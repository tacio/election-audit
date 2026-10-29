#!/usr/bin/env python3
"""Inspect a small reproducible sample of saved logs without writing to acquisition.

This is a raw-message diagnostic, not a session parser or a representative sample
of the national electorate. No timezone normalization or candidate attribution is
performed. The output contains aggregate counters, not voter/mesario identifiers.
"""

import argparse
import hashlib
import io
import json
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .download_tse_logs import manifest_path
else:
    from download_tse_logs import manifest_path


def inspect_member(lines):
    dates = Counter()
    cycles = Counter()
    authorizations = Counter()
    manual_requests = Counter()
    models = set()
    malformed = 0
    first = {}
    last = {}
    for line in lines:
        fields = line.rstrip("\r\n").split("\t")
        if len(fields) != 6:
            malformed += 1
            continue
        timestamp, level, urn, app, message, token = fields
        try:
            # Preserve naive device time; no interpretation as Brasília time.
            parsed = datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            malformed += 1
            continue
        date = parsed.date().isoformat()
        dates[date] += 1
        if message.startswith("Identificação do Modelo de Urna: "):
            models.add(message.split(": ", 1)[1])
        if app != "VOTA":
            continue
        if message == "O voto do eleitor foi computado":
            cycles[date] += 1
            first.setdefault(date, timestamp)
            last[date] = timestamp
        elif message == "Eleitor foi habilitado":
            authorizations[date] += 1
        elif message == "Solicitação de dado pessoal do eleitor para habilitação manual":
            manual_requests[date] += 1
    return {
        "lines_by_date": dict(sorted(dates.items())),
        "completion_messages_by_date": dict(sorted(cycles.items())),
        "authorization_messages_by_date": dict(sorted(authorizations.items())),
        "manual_request_messages_by_date": dict(sorted(manual_requests.items())),
        "first_completion_in_file_order_device_time": first,
        "last_completion_in_file_order_device_time": last,
        "urn_models_observed": sorted(models),
        "malformed_lines": malformed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/tse/2026/turno-2"))
    parser.add_argument("--per-uf", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("data/analysis/log-inspection.json"))
    args = parser.parse_args()
    if not 1 <= args.per_uf <= 10:
        parser.error("--per-uf must be between 1 and 10 for this small diagnostic")
    manifest = manifest_path(args.data).resolve()
    # Fetch a bounded candidate list in a short read-only query. Do not hold the
    # acquisition transaction while decompressing or writing diagnostics.
    with sqlite3.connect(manifest.as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("""SELECT DISTINCT l.uf,l.municipality,l.zone,l.section,
                l.url,l.package_status,f.path,f.sha256 FROM logs l JOIN files f USING(url)
            WHERE l.package_status='Totalizado' ORDER BY l.uf,l.url""").fetchall()
    by_uf = defaultdict(list)
    seen = set()
    for row in rows:
        # Same content may be referenced by multiple runs/packages. This utility
        # samples files, not voters or nationally representative sections.
        if row[7] not in seen:
            by_uf[row[0]].append(row)
            seen.add(row[7])
    sample = []
    for uf, candidates in sorted(by_uf.items()):
        ordered = sorted(candidates, key=lambda row: hashlib.sha256(row[4].encode()).digest())
        for uf, mun, zone, sec, url, status, relative, digest in ordered[: args.per_uf]:
            body = (args.data / relative).read_bytes()
            if hashlib.sha256(body).hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {relative}")
            members = []
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                for member in archive.infolist():
                    if Path(member.filename).name.lower() != "logd.dat":
                        continue
                    with archive.open(member) as raw:
                        members.append(
                            {
                                "member": member.filename,
                                **inspect_member(io.TextIOWrapper(raw, encoding="latin-1")),
                            }
                        )
            sample.append(
                {
                    "uf": uf,
                    "municipality": mun,
                    "zone": zone,
                    "section": sec,
                    "url": url,
                    "sha256": digest,
                    "package_status": status,
                    "members": members,
                }
            )
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Parser diagnostic of available totalized log files; acquisition-biased sample",
        "sampling": "Lowest SHA-256 URL ranks per available UF, deduplicated by object SHA-256",
        "per_uf": args.per_uf,
        "available_unique_files_by_uf": {uf: len(v) for uf, v in by_uf.items()},
        "warning": "Raw event counts are not reconciled votes; naive clocks, mixed rounds and sessions remain unresolved",
        "sample": sample,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"Inspected {len(sample)} files from {len(by_uf)} available UFs; output: {args.output}")
    print("Diagnostic only: not a national sample, session reconstruction, or anomaly finding.")


if __name__ == "__main__":
    main()
