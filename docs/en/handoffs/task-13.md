# Task 13 — Real operational observations

Document-ID: EA-HANDOFF-13 · Revision: 1 · Language: en

`real-operational-v1` adds a bounded real-message adapter without altering existing
structural or operational releases. The official September 2026 log guide was
reviewed at https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema.
`resources/real-log-rules.json` pins exact semantic templates and guide pages for
software 10.23.0.0. It is a reviewed interpretation, not signature certification.

Interfaces: `operational_review.review_object(structural, original, output,
round_number=2, clock=None, witnesses=())` and `review_national(store, output,
round_number=2, max_objects=None, clock_evidence=None)`; CLI function
`operational_review_main(argv)` accepts `--store`, `--output`, `--round`,
`--max-objects`, `--clock-evidence`. Root owns command routing.

Each immutable object directory contains checksummed `artifact.json`,
`events.parquet`, `cycles.parquet`, `sessions.parquet`, and `review.sqlite`.
Parquet rows have JSON string `payload`. Events retain structural IDs and exact
line hashes, adding semantic kind, rules hash, session and readiness. Sessions
retain round/object, official context anchors and publisher witnesses. Cycles
retain anonymous state/method, interruption and nullable duration, never candidate
choice. Source raw text, voter/operator identifiers and authenticators are not
exported. Observed hardware device IDs remain separate from authoritative serials.

Raw originals are hash/size checked and joined against structural locators/hashes
through temporary SQLite; archive expansion and lines are bounded. Official
context requires an exact GAP official-round anchor, matching VOTA round start,
target date and reviewed software version. Other dates, simulation and unsupported
versions cannot silently become official. Manual request alone is not a manual
completion; operator authorization plus successful completion is required. Partial
suspension is distinct from full suspension. Unknown intervening events block
unsupported durations. Clock rules require reviewed exact contiguous event IDs and
matching line-hash anchors; ambiguity remains unavailable. No geographic timezone
default is invented.

The national review uses a disk-backed stream fingerprint index. Equal full
streams of at least two records become copy candidates, retaining all witnesses;
they are not automatically removed or summed as independent histories. Cross-object
replacement/copy adjudication and BU attendance reconciliation remain necessary
before official aggregate-count eligibility. Exposure/gaps and after17 remain
unavailable without separately supported boundaries/clock continuity.

Acceptance: five tests pass for exact classification, both-round official context,
simulation/wrong-round rejection, biometric/manual/partial/full cycles, failed
request handling, clocks, immutable resume and source corruption. Ruff passes.
Actual bounded AC run: `data/phase13/real-run.json` records one acquired log per
round. Round 1 produced 241 completed cycles, one unresolved cycle and one official
session; round 2 produced 232 completed cycles and two official sessions. Both
retain unresolved setup/other sessions and unknown message classes. These are
observations, not attendance reconciliation or national completion. Absolute
clocks remain unavailable. Original source hashes and exact artifacts are in that
run file. Existing immutable releases and acquisition were not modified.

Phase 14 can stream the Parquet session/cycle payloads and join source URLs to its
reviewed section/index population; never infer stable principal identity from a
physical urn or assume one publisher association proves complete coverage.

```sh
rtk proxy .venv/bin/python -B -m unittest discover -s tests -p test_operational_review.py -v
rtk proxy .venv/bin/python -B -m election_audit.operational_review --help
```
