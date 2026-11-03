# Phase 10 — Round identity and corrected first-round acquisition

Document-ID: EA-HANDOFF-10 · Revision: 4 · Language: en

[Português](../../pt-BR/handoffs/task-10.md)

## Outcome — 3 November 2026

Phase 10 is complete. The missing-only resume launched at 2026-10-31T16:56:17Z
(PID 574060) finished at 2026-10-31T23:27:30Z with status `finished` and no error.
All 27 UFs and ZZ were requested: 499176 log versions are saved, 17931 sections are
aggregated, 31 sections have no listed log and 41 have no published auxiliary file.
Every first-round package is `Totalizado` under pleito 3220/election 6257. The
downloader's `national_coverage` flag is false only because of those 72 gap
sections, which stay explicit. On 1 November both rounds were copied to the output
volume and every manifest object was verified by SHA-256 plus a second stat pass
(`certificate-r1.json` and `certificate-r2.json` under `2026/migration-2026-11-01/`).
BWEB, final references, candidacy/location registers and signature/RDV sources for
both rounds remain separate imports owned by later phases.

The sections below are the dated progress log; their "in progress" and "running"
statements are superseded by this outcome.

## Latest recovery — 2026-10-31T16:56:17.247041+00:00

The subsequent run (PID 540761) also stopped during a DNS outage, at
RJ/58335/0126/0088. Its immutable run record ended interrupted at
2026-10-31T16:48:44.441478+00:00 with 322610 downloaded sections, 15074 aggregated,
2 no-log records and 1 error; national coverage remained false. No collector was
active when checked, and a fresh TSE probe returned HTTP 200. Approximately
250 GiB remained on the HDD, above the 20 GiB reserve.

A single missing-only resume now uses PID 574060; command and progress locator
are recorded in `data/phase10/current-acquisition.json` and `data/phase10/resume-launch-20261031T165617Z.json`.
Watch its progress with `tail -f data/phase10/first-round-acquisition-resume-20261031T165617Z.log`. Existing raw bytes and prior logs/
errors remain preserved. Recovery is not completion: verify this run's final
status, expected UF/ZZ coverage and integrity before closing Phase 10.

## Current completion gate — 31 October 2026

Phase 10 remains IN PROGRESS. Work is now sequential: one phase/sub-agent at a
time, complete and review this phase before the next; marimo (Phase 18) is last.
Preserve already produced later-phase work without executing or extending it.

The prior national resume (PID 483059) exited after four DNS-failure attempts in
MG/48950/0194/0172. Its manifest run ended interrupted at 2026-10-31T10:24:47Z,
with 165970 downloaded sections, 9854 aggregated sections, 2 no-log records and
1 error. Earlier failures remain historical records; they are not silently erased.
The manifest contained 331961 file mappings (17944931974 bytes); the HDD had
approximately 249 GiB free. A subsequent official endpoint probe returned HTTP
200, and the prior process was confirmed absent before a single missing-only
resume was launched. The new command, PID and log are preserved in
`data/phase10/resume-launch-2026-10-31.json`. It uses the same verified root and
manifest, 16 workers, 20 requests/second, a 20 GiB reserve and a 30-second timeout.

Do not interpret a launched resume as national completeness. Before Phase 10 can
close, the corrected first-round run must finish without a limit, every UF and ZZ
must be accounted for against official indexes, current acquisition errors must
be resolved or explicitly justified, package identities must agree with 3220/6257,
and available originals must pass integrity checks. Both original mislabeled
manifests and their raw roots remain preserved. Phase 11 must not start meanwhile.


Implemented: validated ElectionDescriptor with election_for_round/coerce_election;
round 1 is pleito 3220/election 6257 on 2026-10-04, round 2 is pleito 3221/election
6258 on 2026-10-25. Acquisition accepts --round (default 2), derives the default
output directory from it, checks official catalog identifiers/date and rejects
wrong-round package URLs before resume. New run_identity rows pin descriptor,
source root and manifest with SHA-256; historical runs are not backfilled.
Inventory URL helpers, coverage identities and snapshots accept an explicit
descriptor. read_manifest/inventory_sources/create_snapshot accept source_manifest;
snapshot CLI exposes --round and --source-manifest. Existing runoff defaults and
frozen snapshots remain readable.

Real source audit: both supplied databases had zero 3220 package mappings and
998412 3221 mappings. Preserve the mislabeled first-round corpus; it is not
relabeled or overwritten. data/phase10/source-audit.json retains read-only counts.
Corrected smoke acquisition selected official 3220/6257 and downloaded one AC
log (102203 bytes), with a finished limited run. The new source root is
/media/tacio/HDD/Data/tse/data/tse/2026/turno-1-verified and its manifest is
.local-state/tse-2026-t1-verified.sqlite. A detached national resume is recorded
in data/phase10/first-round-launch.json, with progress in first-round-acquisition.log.
It runs 16 workers, 20 requests/second and a 20 GiB reserve. Started does not mean
complete; consult process/manifest/status before consuming new source snapshots.

Validation: 31 acquisition regressions, 23 snapshot regressions and 4 new
round/manifest/first-round-snapshot tests passed. Dedicated lint/format checks
cover assigned files. New tests include exact round/date/code selection,
wrong-round resume rejection, and distinct first-round snapshot identities.

Remaining Phase 10 work: national first-round acquisition must finish; BWEB,
final references, candidacy/location registers and signature/RDV sources for
both rounds require separate acquisition/import stages. National-scale source
census and resource preflight are Phase 11. This handoff does not claim national
first-round coverage or completed reconciliation.

Next: Phase 11 uses election_audit.elections and the verified first-round source
paths above; Phase 12 must honor the descriptor when importing official BUs.
