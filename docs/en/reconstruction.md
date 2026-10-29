# Operational reconstruction

Document-ID: EA-RECONSTRUCTION · Revision: 1 · Language: en

[Português](../pt-BR/reconstruction.md) · [Implementation index](implementation-index.md)

Phase 5 reads verified frozen [parse publications](archive-parsing.md), never live
acquisition. `operational-v1` emits candidate sessions, ordered events, anonymous
cycles, lineage, original parser issues and operational summaries. It preserves
all publisher witnesses without multiplying content events. Counts are anonymous
reconstructed cycles, never reconciled votes or candidate/RDV associations.
Acceptance is entirely synthetic; no real message adapter or live pilot has been
validated. The existing three-class structural parser stays `jez-structural-v1`.

```sh
rtk proxy env UV_OFFLINE=1 just reconstruct /path/to/parsed/parses/PARSE_DIGEST --store /path/to/operations
rtk proxy env UV_OFFLINE=1 just reconstruct --help
rtk proxy env UV_OFFLINE=1 just reconstruct /path/to/parsed/parses/PARSE_DIGEST --store /path/to/operations --object-sha256 OBJECT_SHA256 --max-events 100000
```

## Automatic observations and reviewed assertions

Without evidence, member occurrence, original line order, device-column changes
and naive calendar-date changes create conservative candidate boundaries.
`session_kind=unresolved`, target selection and physical device identity stay
unresolved. The device column is an observed reading, not automatically an
authoritative hardware serial. Unknown hardware never merges by section/model.
Advertised package sections and explicit reviewed principal assignments remain
separate; incompatible frozen composition/package context blocks selection.
Setup, training and other-date records remain visible.

The optional JSON evidence input has `version=operational-evidence-v1` and lists
`segments`, `copies`, `semantics`, `clocks`. Each claim requires `rule_id`,
`review_state` (`reviewed` or `unverified`) and `evidence` entries containing exact
`event_id` and `source_line_sha256`. Rule IDs are bounded identifiers, not free
text. Evidence never contains voter/mesario identifiers, message bodies or tokens.
Unknown fields are rejected. Original-event/hash matching validates provenance;
it cannot establish that a human interpretation is correct. `reviewed` is a
supplied review assertion, not a cryptographic certificate. Unverified claims are
retained in metadata and do not alter session selection, semantics or clocks.
Phase 9 must review source meaning and build tested, versioned real adapters.

| Claim list | Supported fields beyond common review/anchors | Meaning |
| --- | --- | --- |
| `segments` | `event_ids`, `session_kind`, `principal_section_id`, `election_id`, `serial`, `software_version`, `software_build`, `start_reason`, `end_reason`, `distinct_history` | Consecutive original physical lines in one member/device; reviewed official/setup/training/other/unresolved context, optional independent hardware/software and boundary evidence |
| `copies` | `canonical_event_ids`, `copied_event_ids` | Distinct consecutive intervals of at least two original lines, equal exact line hashes including newline bytes; explicit reviewed copy decision, no chains |
| `semantics` | `event_id`, `kind` | Reviewed operational interpretation anchored to that original event; original parsed kind remains in `event_evidence` |
| `clocks` | `event_ids`, `section_id`, `election_id`, `timezone`, `clock_adjustment_seconds`, `continuity` | Exact section/election geography, optional IANA zone, signed correction, verified/unknown continuity in one consecutive interval |

Supported session boundary reasons are `unknown`, `opening`, `closing`, `restart`,
`replacement`, `truncated`. Distinct replacement segments never merge merely
because their principal is the same. `distinct_history=true` is a reviewed
assertion that repeated cross-stream history is operationally distinct. Without
that assertion or a verified copied-block rule, possible cross-stream equal-line
history is retained with a readiness blocker. Equal kind/timestamp or repeated
lines within one original stream never trigger automatic deduplication. Copy
lineage retains both original objects, every locator and all observations.

This synthetic example shows the API shape; actual anchors must come from a
verified parse. No source facts are asserted by these illustrative identifiers.

```python
from election_audit.reconstruction import reconstruct_parse

evidence = {
    "version": "operational-evidence-v1",
    "segments": [
        {
            "event_ids": ["EVENT_A", "EVENT_B"],
            "session_kind": "official_vota",
            "principal_section_id": "SECTION_ID",
            "election_id": "ELECTION_ID",
            "rule_id": "reviewed-format-reference-v1",
            "review_state": "reviewed",
            "evidence": [{"event_id": "EVENT_A", "source_line_sha256": "EXACT_LINE_SHA256"}],
        }
    ],
}
path = reconstruct_parse("/path/to/parse", "/path/to/operations", evidence=evidence)
```

## Anonymous transitions

Baseline authorization followed by completion reconstructs a completed cycle with
unknown method. A manual-data request creates a pending history; it never
establishes successful authorization or manual method. Request → authorization →
completion still has unknown method. Only explicit method evidence plus an
authorized successful completion establishes a completed manual cycle.

| Input while tracking a cycle | Result |
| --- | --- |
| Repeated authorization or a new explicit attempt | Retain prior unresolved history, start a new history |
| Completion without active authorization | Unresolved orphan or completion-without-authorization |
| Unknown intervening event or missing physical lines | Preserve unresolved transition history |
| Full suspension | Close a suspended history |
| Partial suspension/resumption | Preserve one interrupted cycle; unsupported active duration stays null |
| Cancellation, abandonment, authorization failure | Close a cancelled history with distinct reason |
| Open history at end | Unresolved or suspended partial history |

Reviewed additional kinds are `authorization_attempt`, `authorization_failed`,
`authorization_manual`, `authorization_biometric`, `authorization_other`,
`suspension_full`, `suspension_partial`, `resumption`, `cancellation`, `abandonment`,
`session_opening`, `session_closing`, `clock_change`. Unknown real text is never
mapped to these by a guessed phrase or broad regular expression.

## Time and eligibility

Raw reading, explicit timezone rule, UTC offset, signed correction, UTC instant,
confidence and evidence remain separate. Municipality exceptions and overseas
locations use exact evidenced section/election rules. No UF default, apparently
early/late heuristic or receipt/publication timestamp supplies a timezone. Missing
zones stay null; ambiguous/nonexistent IANA local times stay unresolved. UTC time
is the corrected local reading minus the evidenced offset. Corrections and
reversals remain visible in original order.

Elapsed durations require a single reviewed continuous clock interval, all
intermediate records, monotonic corrected readings and no unsupported intervening
event or clock change. A zone-free verified interval may support bounded local
elapsed time while UTC remains unavailable. Rule-interval changes invalidate an
unsupported duration, even if the rule IDs happen to match. Completed-cycle
duration starts at successful authorization, excluding a preceding request;
authorization latency is separate. Interrupted cycles have no active duration.
Gaps use adjacent completed cycles in one session, never jump over unresolved
histories or cross replacement boundaries. Domestic after17 in later phases means
strictly after `17:00:00` in `America/Sao_Paulo` on the target date; Phase 5 does
not classify it. Overseas remains separate.

Summaries include observed cycles by state, eligible completed cycles, known and
unknown method denominators, observed manual requests, explicit attempt/failure
denominators, duration and gap eligibility counts, authorization latency,
interruptions and opening/closing evidence. Missing eligible totals remain null.
`known_completed_manual_cycles` counts observed known-method manual completions;
`completed_manual_cycles` stays null if any completed method is unknown. The
manual share applies only to completed cycles with known method. Failure rate
uses explicit observed attempts; the complete attempt population remains unknown.
Feature-specific duration, method and exposure readiness stays separate.

Observed span is not automatically exposure. Exposure requires unique evidenced
opening/closing at the interval boundaries, supported continuous clocks and
resolved interruption intervals; subtract supported interruption seconds. Unknown
boundaries, parse issues, ambiguous copied histories or operational context block
target exposure/count readiness. Full original snapshot coverage and missing
assets remain in the publication. AC–RJ and any object/section sample remain
partial national coverage with the frozen full-index denominator.

## Immutable interface and bounded shards

`reconstructions/DIGEST/` contains checksummed `reconstruction.json` and JSONL
files for the eight session/device/event/cycle/lineage/issue contract tables plus
`event_evidence`, `session_summaries`, `cycle_gaps`, `interruptions`. Staging, fsync,
derived locking and atomic rename prevent successful partial publication. Repeat
runs verify immutable hits; corruption fails explicitly. Inspection works after
raw, snapshot and parse inputs are removed, provided the shared reconstruction
context is retained. Original inputs are never patched. Full population metadata
lives once at `contexts/PARSE_ID/parse.json`; shards reference its validated
relative locator and SHA-256. Relocate the complete store, including `contexts`.

| Python API in `election_audit.reconstruction` | Purpose |
| --- | --- |
| `reconstruct_parse(parse, store, evidence=None, object_sha256=None, max_events=1000000, reader=None)` | Verify a parse/group and publish immutable reconstruction |
| `inspect_reconstruction(path)` | Verify standalone metadata identity and all row-file checksums |
| `load_reconstruction_context(path)` | Verify/load the shared full population and frozen parser context |
| `iter_reconstruction_rows(path, table)` | Verify then stream one contract/intermediate row file |
| `reconstruct_sessions`, `reconstruct_cycles`, `normalize_clocks`, `summarize_operations` | Bounded in-memory work units for fixtures/adapters |

The default bound is unique content events, plus at most ten times that many
publisher witnesses; exceeding either aborts publication. Use repeatable
`--object-sha256` or the Python object list for small related groups. Optional
`object_sha256` on parser `inspect_parse`, `iter_event_witnesses` and
`iter_parsing_issues` verifies/reads only selected content while always checking
the full publication metadata identity. Omitting it preserves full verification.
All selected content's publisher witnesses remain present. The parse publication
metadata/context itself remains in memory, so this is not a fully streaming
national metadata engine.

For a backfill, reuse `FrozenParseReader` to verify/load the parse metadata once
and index associations once. `reader.group(object_sha256)` verifies just that
group's content, returning witness and issue iterators. Passing the reader to
reconstruction also reuses the shared-context publication across shards. Its
`document` is immutable by convention. Structural issues in a group remain
conservative blockers for its target operational summaries.

```python
from election_audit.archive_parsing import FrozenParseReader
from election_audit.reconstruction import reconstruct_parse

reader = FrozenParseReader("/path/to/parsed/parses/PARSE_DIGEST")
for object_sha256 in sorted(reader.artifacts):
    path = reconstruct_parse(
        reader.path,
        "/path/to/operations",
        object_sha256=[object_sha256],
        reader=reader,
    )
```

Independent groups preserve session/cycle identity for unchanged evidence. Include
replacement/copy histories together when needed; cross-group overlap is not
resolved. Phase 6 must record a disjoint content-object partition, reject repeated
event/session/cycle keys when assembling shards, preserve each shard's
`overlap_resolution_scope=selected_object_group_only`, and cannot claim that
independent shards prove no copied histories. Copies or context changes require
a new evidenced reconstruction and replacement of the affected publication.
No DuckDB/Parquet publishing, electoral imports, fitting or fraud labels occur.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_reconstruction.py -v
rtk proxy env UV_OFFLINE=1 just check
```
