"""Run cross-model review rounds with the Codex and Gemini CLIs.

The protocol is docs/en/cross-model-review.md. Reviewers work in a standalone clone of
one commit (no data/, no link to this repository's refs), inside each CLI's sandbox, and
return JSON that follows review/finding.schema.json. Each session's prompt digest, CLI
version and exit status go to the campaign's runs.jsonl; the full transcript stays outside
the repository and is audited for commands that reach paths or hosts the protocol forbids.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from election_audit.types import JSON, Argv

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review"
SCHEMA = REVIEW / "finding.schema.json"
CLONES = Path(os.environ.get("REVIEW_CLONES", Path.home() / ".cache/election-audit-review"))
TRANSCRIPTS = Path(
    os.environ.get("REVIEW_TRANSCRIPTS", Path.home() / "data/election-audit-stage/review")
)
REVIEWERS = ("codex", "gemini")
MODELS = {"codex": "gpt-6.1-sol", "gemini": "gemini-3.8-flash-high"}
"""Pinned per run, so that a change of a CLI's default never changes the reviewer silently."""
LANES = {"codex": re.compile(r"(?!.*claude)"), "gemini": re.compile(r"gemini-")}
"""Each lane must run its own provider's model; a Claude model would review its own work."""
ROUNDS = ("R1", "R3", "R5")
UV_CACHE = os.environ.get("UV_CACHE_DIR", "/tmp/election-audit-uv-cache")
FORBIDDEN = re.compile(
    r"election-audit-stage|\.local-state|(~|\$HOME|/home/[^/\s'\"]+)/data\b"
    rf"|{re.escape(str(ROOT))}(?![-\w])|\b(curl|wget|ssh|scp|rsync|nc)\b|https?://"
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def campaign_dir(campaign: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", campaign):
        raise SystemExit(f"campaign id must be lowercase letters, digits and dashes: {campaign}")
    return REVIEW / "campaigns" / campaign


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def packets() -> dict[str, Path]:
    return {path.stem.split("-", 1)[0]: path for path in sorted((REVIEW / "packets").glob("*.md"))}


def clone_path(campaign: str, sha: str) -> Path:
    return CLONES / f"{campaign}-{sha[:12]}"


def prepare(campaign: str, ref: str) -> Path:
    """A standalone clone of one commit with its own environment; the campaign pins it."""
    sha = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    folder = campaign_dir(campaign)
    record = folder / "campaign.json"
    if not record.exists():
        folder.mkdir(parents=True)
        record.write_text(
            json.dumps({"campaign": campaign, "reviewed_commit": sha, "created": now()}, indent=2)
            + "\n"
        )
    clone = clone_path(campaign, sha)
    if clone.exists():
        print(f"clone exists: {clone}")
        return clone
    CLONES.mkdir(parents=True, exist_ok=True)
    git("clone", "--quiet", "--no-local", "--no-checkout", str(ROOT), str(clone))
    git("checkout", "--quiet", "--detach", sha, cwd=clone)
    git("remote", "remove", "origin", cwd=clone)
    env = os.environ | {"UV_OFFLINE": "1", "UV_CACHE_DIR": UV_CACHE}
    subprocess.run(
        ["uv", "sync", "--locked", "--all-extras", "--quiet"], cwd=clone, env=env, check=True
    )
    print(f"clone ready: {clone} at {sha}")
    return clone


def ledger(campaign: str, packet: str) -> list[JSON]:
    path = campaign_dir(campaign) / "ledger.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [row for row in rows if row.get("packet") == packet]


def build_prompt(
    campaign: str, round_name: str, reviewer: str, packet: str, sha: str, fixes: str | None
) -> str:
    """The round's instructions, the packet and, after R1, the ledger rows of the packet."""
    parts = [
        f"Campaign `{campaign}`, round {round_name}. You are reviewer `{reviewer}`. "
        f"Packet {packet}. The checkout is at commit {sha}. In your JSON, set reviewer to "
        f'"{reviewer}", packet to "{packet}", round to "{round_name}" and commit to "{sha}".',
        (REVIEW / "prompts" / f"{round_name}.md").read_text(),
        packets()[packet].read_text(),
    ]
    rows = ledger(campaign, packet)
    if round_name == "R3":
        parts.append(
            "# Ledger rows for this packet\n\nEach row lists its `sources`; rows whose sources "
            f"include `{reviewer}` are yours, the others came from the other reviewer.\n\n"
            + "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        )
    if round_name == "R5":
        if not fixes:
            raise SystemExit("R5 needs --fixes A..B, the commit range that holds the fixes")
        fixed = [row for row in rows if row.get("disposition") in {"confirmed", "partly-confirmed"}]
        parts.append(
            f"# Fixes to verify\n\nCommit range: `{fixes}` (run `git log {fixes}` and "
            f"`git diff {fixes}`).\n\n"
            + "\n".join(json.dumps(row, ensure_ascii=False) for row in fixed)
        )
    return "\n\n---\n\n".join(parts) + "\n"


def command_texts(transcript: Path) -> list[str]:
    """Commands and tool parameters from a Codex or Gemini event stream; outputs are skipped."""
    texts = []
    for line in transcript.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item") or {}
        if isinstance(item, dict) and item.get("type") == "command_execution":
            texts.append(str(item.get("command", "")))
        step = event.get("step_update") or {}
        info = step.get("tool_info") if isinstance(step, dict) else None
        if (
            isinstance(info, dict)
            and step.get("state") == "ACTIVE"
            and info.get("name") != "finish"
        ):
            texts.append(json.dumps(info.get("parameters", {}), ensure_ascii=False))
    return texts


def audit(transcript: Path) -> list[str]:
    return [text[:300] for text in command_texts(transcript) if FORBIDDEN.search(text)]


def gemini_result(transcript: Path) -> JSON | None:
    for line in reversed(transcript.read_text(errors="replace").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = event.get("result") if isinstance(event, dict) else None
        if isinstance(result, dict):
            structured = result.get("structured_output")
            if isinstance(structured, dict):
                return structured
            try:
                return json.loads(result.get("response", ""))
            except json.JSONDecodeError:
                return None
    return None


def version(tool: str) -> str:
    executable = {"codex": "codex", "gemini": "agy"}[tool]
    try:
        done = subprocess.run([executable, "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        return "missing"
    return (done.stdout or done.stderr).strip().splitlines()[0] if done.returncode == 0 else "?"


def session(args: argparse.Namespace, reviewer: str, packet: str, sha: str, lock: Any) -> bool:
    """Run one session; False when it failed fast (quota or start-up error)."""
    folder = campaign_dir(args.campaign)
    report = folder / args.round / f"{packet}.{reviewer}.json"
    if report.exists():
        print(f"skip {report.relative_to(ROOT)}: exists (outputs are never overwritten)")
        return True
    prompt = build_prompt(args.campaign, args.round, reviewer, packet, sha, args.fixes)
    clone = clone_path(args.campaign, sha)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    transcript = TRANSCRIPTS / args.campaign / f"{args.round}-{packet}-{reviewer}-{stamp}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    model = getattr(args, f"{reviewer}_model")
    if not LANES[reviewer].match(model):
        raise SystemExit(f"the {reviewer} lane cannot run model {model}")
    if reviewer == "codex":
        last = transcript.with_suffix(".last.json")
        command = ["codex", "exec", "-s", "workspace-write", "--ephemeral", "-C", str(clone)]
        command += ["--json", "--output-schema", str(SCHEMA), "-o", str(last)]
        command += ["-c", f'model_reasoning_effort="{args.effort}"']
        command += ["-m", model]
        command += ["-"]
        stdin = prompt
    else:
        command = ["agy", "--sandbox", "--output-format", "stream-json"]
        command += ["--json-schema", str(SCHEMA), "--effort", args.effort]
        command += ["--model", model]
        command += ["-p", prompt]
        stdin = ""
    started, clock = now(), time.monotonic()
    with transcript.open("w") as out:
        try:
            done = subprocess.run(
                command,
                cwd=clone,
                input=stdin,
                stdout=out,
                stderr=subprocess.PIPE,
                text=True,
                timeout=args.timeout_minutes * 60,
                env=os.environ | {"UV_OFFLINE": "1", "UV_CACHE_DIR": UV_CACHE},
            )
            status, stderr = done.returncode, done.stderr
        except subprocess.TimeoutExpired:
            status, stderr = "timeout", ""
    result: JSON | None = None
    if reviewer == "codex":
        last = transcript.with_suffix(".last.json")
        try:
            result = json.loads(last.read_text()) if last.exists() else None
        except json.JSONDecodeError:
            result = None
    else:
        result = gemini_result(transcript)
    flagged = audit(transcript)
    if result is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    row = {
        "round": args.round,
        "packet": packet,
        "reviewer": reviewer,
        "commit": sha,
        "fixes": args.fixes,
        "cli": version(reviewer),
        "model": model,
        "effort": args.effort,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "started": started,
        "minutes": round((time.monotonic() - clock) / 60, 1),
        "status": status if result is not None or status != 0 else "no-report",
        "report": report.name if result is not None else None,
        "transcript": transcript.name,
        "findings": len(result.get("findings", [])) if result else None,
        "boundary_flags": flagged,
        "stderr_tail": stderr[-500:] if status != 0 else "",
    }
    with lock:
        with (folder / "runs.jsonl").open("a") as runs:
            runs.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"{args.round} {packet} {reviewer}: status {status}, {row['minutes']} min, "
            f"{row['findings']} findings, {len(flagged)} boundary flags"
        )
    return not (status != 0 and row["minutes"] < 1)


def run(args: argparse.Namespace) -> None:
    folder = campaign_dir(args.campaign)
    pinned = json.loads((folder / "campaign.json").read_text())["reviewed_commit"]
    sha = git("rev-parse", "--verify", f"{args.commit}^{{commit}}") if args.commit else pinned
    if not clone_path(args.campaign, sha).exists():
        raise SystemExit(f"no clone for {sha[:12]}; run: prepare {args.campaign} --commit {sha}")
    if args.round == "R5" and sha == pinned:
        raise SystemExit("R5 reviews the fixed commit; pass --commit with the commit after fixes")
    chosen = list(packets()) if args.packet == "all" else args.packet.split(",")
    unknown = set(chosen) - set(packets())
    if unknown:
        raise SystemExit(f"unknown packets: {sorted(unknown)}")
    reviewers = REVIEWERS if args.reviewer == "all" else (args.reviewer,)
    for reviewer in reviewers:
        executable = {"codex": "codex", "gemini": "agy"}[reviewer]
        if shutil.which(executable) is None:
            raise SystemExit(f"{executable} is not on PATH")
    lock = threading.Lock()

    def lane(reviewer: str) -> None:
        for packet in chosen:
            if not session(args, reviewer, packet, sha, lock):
                print(f"{reviewer}: failed within a minute, stopping this lane (quota?)")
                return

    threads = [threading.Thread(target=lane, args=(reviewer,)) for reviewer in reviewers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def main(argv: Argv = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="clone one commit and pin it to a campaign")
    prep.add_argument("campaign")
    prep.add_argument("--commit", default="HEAD")
    for name in ("run", "prompt"):
        sub = commands.add_parser(name, help=f"{name} a round for reviewers and packets")
        sub.add_argument("campaign")
        sub.add_argument("round", choices=ROUNDS)
        sub.add_argument("--reviewer", default="all", choices=("all", *REVIEWERS))
        sub.add_argument("--packet", default="all", help="all, or comma-separated packet ids")
        sub.add_argument("--commit", help="reviewed commit (default: the campaign's)")
        sub.add_argument("--fixes", help="R5 only: commit range A..B holding the fixes")
    run_parser = commands.choices["run"]
    run_parser.add_argument("--effort", default="high", choices=("medium", "high", "xhigh"))
    run_parser.add_argument("--codex-model", default=MODELS["codex"])
    run_parser.add_argument("--gemini-model", default=MODELS["gemini"])
    run_parser.add_argument("--timeout-minutes", type=int, default=90)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.campaign, args.commit)
    elif args.command == "run":
        run(args)
    else:
        folder = campaign_dir(args.campaign)
        pinned = json.loads((folder / "campaign.json").read_text())["reviewed_commit"]
        sha = git("rev-parse", "--verify", f"{args.commit}^{{commit}}") if args.commit else pinned
        reviewer = "codex" if args.reviewer == "all" else args.reviewer
        packet = next(iter(packets())) if args.packet == "all" else args.packet
        sys.stdout.write(build_prompt(args.campaign, args.round, reviewer, packet, sha, args.fixes))


if __name__ == "__main__":
    main()
