# Frozen archive parsing

Document-ID: EA-ARCHIVE-PARSING · Revision: 1 · Language: en

[Português](../pt-BR/archive-parsing.md) · [Implementation index](implementation-index.md)

Phase 4 reads only completed [snapshots](snapshots.md). `parse_snapshot` calls
`inspect_snapshot(..., verify_objects=True)` and `snapshot_tables`, then opens
the frozen relative `source_object.storage_locator`. Original acquisition paths
under `payload.inventory` are evidence, never parser inputs. Acquisition and
snapshot bytes remain unchanged. No real corpus parsing has been run; the bounded
real-data pilot belongs to Phase 9. AC–RJ remains partial national coverage, and
section samples retain the frozen whole-UF denominator.

```sh
rtk proxy env UV_OFFLINE=1 just parse /path/to/derived/SNAPSHOT_DIGEST --store /path/to/parsed
rtk proxy env UV_OFFLINE=1 just parse --help
```

The command prints a completed publication directory. `--store` must be outside
both the immutable snapshot and original acquisition root. Selected asset names
ending in `log.dat`, `.jez` or `.zip` identify candidate objects; no package status
filter silently excludes setup or unknown contexts. Missing observations and
unmapped historical advertisements remain explicit. Metadata indexes are not
mistaken for log archives. These commands are illustrative, not a pilot run.

The archive reader validates ZIP directory structure before allocating `ZipFile`
metadata. It streams every permitted member through CRC/length validation before
parsing it, including non-log members. Nested ZIP/JEZ members are seekable private
temporary files on disk; no member path is extracted. Temporary files are bounded
by per-member and cumulative expanded-byte guards. JSONL events and issues stream
to disk rather than accumulating a corpus in memory. ZIP64, multi-disk and
nonstandard directory layouts produce explicit unsupported/invalid issues; they
are not reported as successful decodes. CRC and SHA-256 do not verify signatures.

Each locator retains every original member name, zero-based occurrence among
equal names in its containing archive, and zero-based central-directory index.
Duplicate names and equal contents remain separate occurrences, including nested
duplicates. Original root archive filenames/URLs remain in the separate frozen
observation and package-asset associations. One-based line spans are exact;
unknown original byte offsets stay null. Ordering follows archive member order
and original line order; no timestamp sort occurs.

| Guard / CLI option | Default | Behavior at limit |
| --- | --- | --- |
| `--max-archive-bytes` | `536870912` | Reject larger ZIP container |
| `--max-member-bytes` | `134217728` | Skip larger member with issue |
| `--max-total-bytes` | `536870912` | Cumulative expanded bytes, including nested containers |
| `--max-directory-bytes` | `4194304` | Bound central-directory memory before ZIP decoding |
| `--max-members` | `10000` | Global member count across nesting |
| `--max-depth` | `4` | Root depth is zero; each nested container adds one |
| `--max-line-bytes` | `65536` | Physical bytes including line ending; drain oversized line |
| `--max-lines` | `2000000` | Global original physical-line count |
| `--max-issues` | `10000` | Retain this many diagnostics plus one `diagnostic_limit` marker |

All limits must be positive integers and are part of cache identity. A skipped
member, malformed line, corruption or limit produces `partial`; surviving events
remain usable as evidence with that limitation. `complete` means structural
decoding completed, never electoral eligibility, session completeness or votes.
When diagnostics overflow, `issues_seen` still counts encountered diagnostics;
the retained marker makes the truncation explicit. Resource/disk failures abort
publication rather than produce a successful artifact.

`logd.dat` members (case-insensitive basename, either path separator) use Latin-1
and six tab-separated columns: timestamp, level, device, application, message,
token. Exact valid naive device timestamps are retained, without timezone or
round inference. Only numeric device identity and bounded application identity
are selected. Malformed records retain a locator and bounded structured error
reason, without raw samples or exception text. Voter/mesario identifiers, message
bodies and sensitive tokens are never selected into events or diagnostics.

| Exact VOTA message | `event_kind` |
| --- | --- |
| `O voto do eleitor foi computado` | `completion_message` |
| `Eleitor foi habilitado` | `authorization_message` |
| `Solicitação de dado pessoal do eleitor para habilitação manual` | `manual_request_message` |

These are the only three decoded classes in `jez-structural-v1`. All other
messages/applications remain `unknown` with `unsupported_message_class` evidence.
Every event keeps `selection_state=context_unresolved`, including setup and mixed
date/round contexts. Later semantics require versioned adapter extensions against
original evidence. A manual request is not a completed authorization or cycle.
Completion messages are not reconciled vote totals.

`source_line_sha256` hashes the exact original physical line, including its
original CR/LF bytes, when present. It preserves evidence that different unknown
messages differ without selecting their text. It is not an event identity or a
deduplication decision. Event identity includes original object, complete member
occurrence locator, source line and parser/config version. Repeated equal lines
at the same second still produce separate events. Copied-block decisions in
Phase 5 require explicit evidence and a reconstruction rule; normalized kinds and
timestamps alone cannot establish equivalence.

`cache/KEY/` contains `events.jsonl`, `issues.jsonl`, `artifact.json` and
`artifact.json.sha256`. The key hashes content SHA-256, parser version and the
whole configuration. Every cache hit verifies metadata identity and all streamed
file lengths/checksums. Byte-identical objects reuse content parsing across
packages and snapshots. Damaged caches are moved to `.corrupt-*` for evidence,
then rebuilt; completed artifacts are never patched. Private staging, fsync,
derived-store locks and atomic rename make restarts safe. Abandoned
`.parse-building-*` directories are ignored, with cleanup a separate action.

`parses/PUBLICATION_DIGEST/` contains checksummed `parse.json`. This immutable
publication binds cached hashes to the snapshot ID, all matching original source
observations and package assets, frozen election/section/package context tables,
unknown historical advertisements, missing assets and original coverage summary.
Associations do not participate in content-cache identity. Same bytes therefore
do not erase publisher witnesses or imply one operational session.

| Python API in `election_audit.archive_parsing` | Use |
| --- | --- |
| `parse_snapshot(snapshot, store, config=ParseConfig())` | Verify frozen inputs; return publication path |
| `inspect_parse(path)` | Verify publication and referenced content, independently of raw inputs |
| `inspect_artifact(path)` | Verify one immutable cached content artifact |
| `iter_event_witnesses(path)` | Stream events per snapshot/source observation, retaining all package assets |
| `iter_lineage(path)` | Stream contract-shaped `record_lineage` for event witnesses |
| `iter_parsing_issues(path)` | Stream snapshot-bound `parsing_issue` contract rows |
| `parse_object(source, store, config=..., expected_sha256=...)` | Internal/fixture content API; production callers use frozen snapshot API |

`event_id` identifies a content occurrence; `witness_event_id` additionally scopes
it to snapshot and source observation. Phase 5 must choose operational sessions
with evidence before aggregating witnesses. The event/witness JSONL structures
are intermediate artifacts, not premature `selected_event` or voting-session
contract rows. No session reconstruction, timezone conversion, electoral imports,
DuckDB/Parquet publication, feature fitting or fraud labeling occurs here.

Acceptance used only isolated synthetic fixtures: nested/duplicate members, CRC
corruption, missing logs, malformed/oversized lines, all guards, repeated equal
messages, mixed contexts, redaction, distinct unknown fingerprints, cache damage,
interruption, frozen-only reads and multiple package/snapshot associations. All
15 parser fixtures and all 83 repository tests passed; recipe help also passed.

```sh
rtk proxy env UV_OFFLINE=1 UV_CACHE_DIR=/tmp/election-audit-uv-cache uv run --locked python -m unittest discover -s tests -p test_archive_parsing.py -v
rtk proxy env UV_OFFLINE=1 just check
rtk proxy env UV_OFFLINE=1 just parse --help
```
