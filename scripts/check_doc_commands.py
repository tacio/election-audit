"""Inspect documentation examples without executing their operations or SQL."""

import argparse
import io
import re
import shlex
from contextlib import redirect_stdout
from pathlib import Path

import duckdb

from election_audit.cli import main as cli_main
from scripts.check_docs import FENCES, ROOT, document_paths

CLI_COMMANDS = {
    "doctor",
    "download",
    "resume",
    "inspect",
    "snapshot",
    "snapshot-inspect",
    "parse",
    "reconstruct",
    "build",
    "validate",
    "query",
    "report",
    "import-results",
    "analyze",
    "demo",
    "review-bundle",
    "reproduce",
    "pilot",
    "backfill",
}


def help_flags(command):
    """Only this fixed --help invocation can run; example tokens never execute."""
    if command == "doctor":
        return {"--help"}
    stream = io.StringIO()
    with redirect_stdout(stream):
        try:
            cli_main([command, "--help"])
        except SystemExit as exc:
            if exc.code != 0:
                raise
    return set(re.findall(r"--[a-z][a-z0-9-]*", stream.getvalue()))


def check_commands(root=ROOT):
    root = Path(root)
    recipes = set(
        re.findall(r"^([a-z][a-z-]*)\b[^\n]*:\s*$", (root / "justfile").read_text(), re.M)
    )
    cache, errors, counts = {}, [], {"commands": 0, "sql_statements": 0, "help_invocations": 0}
    with duckdb.connect(config={"enable_external_access": "false"}) as db:
        for path in document_paths(root):
            for block in FENCES.findall(path.read_text()):
                language = block.splitlines()[0]
                if language == "```sql":
                    try:
                        statements = db.extract_statements("\n".join(block.splitlines()[1:-1]))
                        counts["sql_statements"] += len(statements)
                    except Exception as exc:
                        errors.append(f"{path.relative_to(root)}: SQL syntax: {type(exc).__name__}")
                if language not in {"```sh", "```bash", "```shell"}:
                    continue
                shell = "\n".join(block.splitlines()[1:-1]).replace("\\\n", " ")
                for line in shell.splitlines():
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    try:
                        tokens = shlex.split(line)
                    except ValueError:
                        errors.append(f"{path.relative_to(root)}: invalid shell quoting")
                        continue
                    command, forwarded = None, []
                    if "just" in tokens:
                        index = tokens.index("just")
                        if index + 1 == len(tokens) or tokens[index + 1].startswith("-"):
                            continue
                        recipe = tokens[index + 1]
                        if recipe not in recipes:
                            errors.append(f"{path.relative_to(root)}: unknown recipe {recipe}")
                            continue
                        counts["commands"] += 1
                        if recipe in CLI_COMMANDS:
                            command, forwarded = recipe, tokens[index + 2 :]
                    elif "election-audit" in tokens:
                        index = tokens.index("election-audit")
                        if index + 1 < len(tokens):
                            command, forwarded = tokens[index + 1], tokens[index + 2 :]
                            counts["commands"] += 1
                    if command:
                        if command not in CLI_COMMANDS:
                            errors.append(f"{path.relative_to(root)}: unknown CLI {command}")
                            continue
                        if command not in cache:
                            cache[command] = help_flags(command)
                            counts["help_invocations"] += 1
                        # Parse flags only; values (including SQL with -- comments)
                        # and paths never become shell commands or file reads.
                        for token in forwarded:
                            if re.fullmatch(r"--[a-z][a-z0-9-]*(?:=.*)?", token):
                                flag = token.split("=", 1)[0]
                                if flag not in cache[command]:
                                    errors.append(
                                        f"{path.relative_to(root)}: unknown flag {command} {flag}"
                                    )
                        if "--sql" in forwarded:
                            sql_index = forwarded.index("--sql") + 1
                            if sql_index >= len(forwarded):
                                errors.append(f"{path.relative_to(root)}: --sql missing value")
                            else:
                                try:
                                    counts["sql_statements"] += len(
                                        db.extract_statements(forwarded[sql_index])
                                    )
                                except Exception as exc:
                                    errors.append(
                                        f"{path.relative_to(root)}: SQL syntax: {type(exc).__name__}"
                                    )
    return errors, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors, counts = check_commands(args.root)
    for error in errors:
        print(error)
    print(counts)
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
