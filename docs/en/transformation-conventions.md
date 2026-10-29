# Transformation conventions

Document-ID: EA-TRANSFORMATION-CONVENTIONS · Revision: 1 · Language: en

[Português](../pt-BR/transformation-conventions.md)

1. **Immutable inputs.** Resolve the authoritative manifest with `manifest_path(root)`
   and `manifest-location.json`. Use a consistent read transaction or SQLite backup,
   never copy a live database file without its committed WAL. Preserve original
   objects and active acquisition. Freeze URL-to-object observations, run/metadata
   associations, failed attempts, expected coverage and policy. A historical mapping
   that cannot be recovered is explicitly unknown; the current `files` mapping is
   not evidence of old bytes. No national downloads are part of this contract.
2. **Identity.** Scope section/location/contest identities to election. Opaque IDs use
   a versioned namespace plus a digest of canonical JSON natural-key tuples (sorted
   keys, UTF-8, no insignificant whitespace). Preserve natural keys and identity-rule
   version; never key a device/session/package/result by section alone. Do not merge
   unknown devices by model. A contract major change requires a new publication;
   append-only observations/results remain immutable and derivations pin parser,
   transformation, selection and schema versions.
3. **Source records.** A locator records each nested archive segment, original member
   name and occurrence index (duplicate ZIP names are possible), plus original
   byte/line/record span when known. Event identity includes object/member occurrence,
   source line/sequence and parser version. Never derive it solely from timestamp
   and message text. Never invent a byte offset after decoding. Every derived row
   links to at least one original record; keep duplicate/conflict witnesses too.
   Select only operationally necessary fields. Do not expose voter/mesario IDs or
   unnecessary sensitive tokens in structured events/issues; original bytes remain
   preserved separately with their existing access boundaries.
4. **Decode before select.** Preserve raw token and original ordering; validate
   encoding, source headers, widths and meanings by schema version. Keep setup,
   training and other-round events with selection reasons. Reconstruct official
   VOTA sessions, transitions, replacement devices and cycles before extracting
   features. A manual-data request may be cancelled. Completed cycles, suspensions,
   attempts and unresolved cases are distinct. RDV order cannot identify choices
   in anonymous cycles.
5. **Clocks.** Preserve device reading, timezone rule and evidence, offset, adjustment
   and confidence separately. Verify municipality exceptions and overseas rules;
   never infer zone from an apparently early/late vote. Unresolved absolute time
   blocks absolute-time features but may permit count checks or bounded durations.
   Domestic after17 means strictly after 17:00:00 Brasilia (`America/Sao_Paulo`) on
   target date; overseas is separate. Receipt, processing, generation, publication,
   observation, opening/closing and transmission are not substitutes.
6. **Deduplicate with evidence.** Byte identity deduplicates objects, not necessarily
   sessions or results. Verified copied/overlapping event blocks require explicit
   lineage and a reconstruction rule. Repeated message text/second-resolution time
   can be legitimate. Replacement sessions must not be summed through every package
   witness. Keep unresolved duplication unavailable rather than guess.
7. **Join and sum safely.** Select one canonical eligible result per
   `(snapshot_id, principal_section_id, contest_id)` before aggregating. Validate
   uniqueness on the right of every many-to-one join and preserve row counts/key
   counts. Aggregate long choices to result grain before attaching totals. Never
   sum electorate/attendance after joining totals to multiple choices, composition
   members, sessions, package witnesses or lineage. Use member-to-principal only to
   resolve the unique analytical principal; historical harmonization aggregates
   each disjoint population exactly once. Incomparable crosswalks stay unavailable.
8. **Reconcile before publish.** Foreign keys, matching election/contest contexts,
   composition self-maps/acyclicity, canonical status/identity, nonnegative counts,
   choice completeness, category accounting, turnout/electorate definitions and
   expected population must be checked beyond structural validation. Compare
   municipality/UF/BR including ZZ on coherent snapshots. Separate coverage gaps
   from numerical discrepancies. Retain corrections/decreases and competing results.
   SHA-256/CRC checks do not verify digital signatures or voter intent.
9. **Publish availability.** Count expected members and unique principals separately;
   record installed/non-installed, missing, parser failures, exclusions and unknowns.
   No silent drop or null-to-zero imputation. Readiness is per feature/unit; record
   denominator and missing reason. AC–RJ acquisition order is partial national
   coverage and cannot support national inference. Other rounds/history need explicit
   schema-validated imports. No fitting or fraud labels in this pipeline phase.

A synthetic join example fixes the accounting rule. One result has electorate
`100`, attendance `80`, candidate counts `45` and `30`, blank `3`, null `2`, and
special/unresolved `0`. There is one totals row and four choice rows. Joining
choices and summing repeated attendance would produce `320`; correct attendance
is `80`. Two member sections pointing to that principal still represent `80`,
not `160`. This example is artificial and says nothing about observed data.

```sql
-- Synthetic example only; no acquisition table is queried.
WITH totals(result_version_id, attending_voters) AS (VALUES ('r1', 80)),
choices(result_version_id, vote_count) AS
    (VALUES ('r1', 45), ('r1', 30), ('r1', 3), ('r1', 2)),
choice_totals AS (
    SELECT result_version_id, SUM(vote_count) AS ballots
    FROM choices GROUP BY result_version_id
)
SELECT t.attending_voters, c.ballots
FROM totals t JOIN choice_totals c USING (result_version_id);
```

Expected result: `80`, `80`. Do not use `SUM(DISTINCT attending_voters)` to repair
a multiplied join: equal totals in different sections are legitimate.
