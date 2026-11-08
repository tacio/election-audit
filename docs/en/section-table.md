# Section feature table v4 (Phases 22 and 20b)

Document-ID: EA-SECTION-TABLE · Revision: 4 · Language: en

[Português](../pt-BR/section-table.md) · [Implementation index](implementation-index.md)

`section-table build` writes, for one election year, one row per principal section
and round. Each row carries its composition, polling place, voter-profile covariates,
device model and software, clock rule, integrity status and operational measures.
The table also defines a cross-round crosswalk of harmonized units and a population
ledger. It is the input of the Tier 2 models
([study protocol](../../research/analysis-plan.md#7-tier-2-statistical-analysis)).
Nothing is imputed: a value that is missing, conflicting or unresolved stays null,
and every measure family has an availability state and reason.

## Data access

Results and operational measures are written only under `restricted/`. Before the
Phase 23 freeze, code reads them and people don't, except for the development UFs
([study protocol, section 2](../../research/analysis-plan.md#2-what-has-already-been-seen)).
The public part (`sections.parquet`, `units.parquet`, `ledger.json`) holds keys,
covariates, device, clock and availability fields, and counts.

## Inputs

| Input | Source | Used for |
| --- | --- | --- |
| BWEB, presidential rows, both rounds | Phase 19 `resultados-<year>-boletim-de-urna` | Results, composition (aggregated sections), BU metadata |
| Voter profile by section, polling places | Phase 19 `eleitorado-<year>` | Covariates, location keys, coordinates |
| Semantic pass `session-aggregates-v4`, both rounds | `semantic-pass run` | Operational measures, model, software, clock evidence |
| Phase 20 releases (2026 only) | `integrity-check` | I1–I9 status, BU-side model and software |
| Protection exclusions (2026) | `data/national/phase11-protection-2026-10-31/exclusions.json` | The 596 protected sections stay `outside_scope` |

Version 4 of the table (`section-features-v4`, `session-aggregates-v4`) reads the
semantic pass with session rules `sessions-v2`; its rules are unchanged.
`session-aggregates-v3` added nine columns per session and changed nothing else.
Nationally, in both years and rounds, every column shared with the earlier release
is equal in every session, segment and object row
([semantic pass](semantic-pass.md#version-3-phase-22)). The new columns:

- `model`: from `Identificação do Modelo de Urna: UE####` in the same stream.
- `software_version`: from `Versão da aplicação: …`, read in the VOTA session.
- Clock evidence recorded before the session, cumulative per stream:
  - operator clock settings from the ADH app (`clock_adh_before`, plus the typed
    shift `clock_adh_shift_s_before`);
  - time-zone adjustments (`clock_tz_shifts_before`, `clock_tz_shift_s_before`);
  - daylight-saving adjustments (`clock_dst_before`).
- `configured_close`: the closing time the urn prints when someone tries to close
  early.
- `segment_ordinal`: links the session to its context segment.

## Rules

**Population.** A round's sections are the union of four sources:

- BWEB principal sections;
- polling-place principal sections;
- sections named by a log;
- for 2026, sections in the Phase 20 releases.

A section's members are its principal plus the aggregated sections BWEB lists.
Unparseable compositions are counted in the manifest.

**Copies of one session.** An urn's package can hold the same log twice, from
internal memory (`…MI.jez`) and from external memory (`…ME.jez`); this happens when
the urn was replaced. Copies are recognized by block lineage, never by message text
or time. Two official sessions of a section are copies when all three match:

- the device;
- the block start, meaning the hash of the first line of the official-round segment;
- the session's rank inside that block.

The copy with the longest block is kept. If a shorter copy has more completions,
that is a conflict, and the section's operational measures become `unavailable`
(`conflict`). Sessions without a segment link are never merged. Whether the copies
are equal as prefixes is verified in Phase 20b.

**Device.** In 2026 the model comes from the urn's signature file (Phase 20
`equipment`), and it is compared with the model of the section's last official
session, the urn that emitted the BU. In 2022 the model comes from the logs only.
Sections whose urn was replaced keep every model in `log_models_json`.

**Closing time.** Urn clocks run on local time. Voting closes at 17:00 Brasília time
in Brazil, and at 17:00 local time abroad. The expected closing time on the urn's
clock comes from the legal time zones (Decreto 2.784/1913, Art. 2, as amended by
Lei 12.876/2013):

| Rule | Where | Closing reading |
| --- | --- | --- |
| `law_uf` | UFs with a single zone (AC −2 h; MT, MS, RO, RR −1 h; the others 0 h) | 15:00, 16:00 or 17:00 |
| `law_noronha` | Fernando de Noronha (PE) | 18:00 |
| `abroad` | ZZ | 17:00 |
| `am_configured` | Amazonas, split by a line rather than by municipality | The configured close printed by the municipality's urns, when every observation in the year agrees with the list below |
| `am_list` | Amazonas municipalities whose urns printed no configured close | 15:00 for the eleven municipalities on Acre time, 16:00 for the others |
| `unresolved` | Amazonas municipalities whose printed closes disagree with each other or with the list | Unavailable |

The eleven Amazonas municipalities on Acre time (UTC−5) are pinned in
`resources/am-acre-time-municipalities.json` with their sources: TRE-AM notices for
2024 and 2026, TSE's polling-place files and the urns' own prints
([observation O12](observations.md#operations)). TSE publishes no dataset of
municipal time zones ([T10](observations.md#transparency)).

**Clock state.** The first condition that matches decides the state. Time-of-day
measures need `ok` or `adjusted`.

| State | Meaning |
| --- | --- |
| `no_sessions` | No official session |
| `no_close_rule` | No closing rule applies |
| `off_election_date` | A session starts on another date |
| `backstep` | The clock steps backwards inside a session |
| `overlap` | Two sessions overlap |
| `close_conflict` | A configured close differs from the rule |
| `adjusted` | An operator, time-zone or daylight-saving adjustment before the session |
| `ok` | None of the above |

**Measures** (`restricted/sections.parquet`):

- completed, suspended, cancelled and unresolved cycles by authorization method;
- non-biometric completions;
- completions per reading hour, and completions at or after the expected close
  (hour bins);
- active seconds (first to last completion, per session);
- the longest gap;
- manual requests and orphan completions.

Operational measures are `partial` when cycles stay unresolved or completions have
no cycle.

**Crosswalk.** A harmonized unit is a connected component of registered sections
linked to their principal in either round. So sections that were aggregated
differently in the two rounds are compared as a whole and never mixed with other
voters. Units are typed:

| Kind | Meaning |
| --- | --- |
| `same_principal` | The same principal in both rounds |
| `recombined` | The composition changed between rounds |
| `one_round_only` | Present in only one round |

A unit is `comparable` when every principal in both rounds has ready results.
`restricted/unit_votes.parquet` sums votes by votable number per unit and round.

## Command

```sh
just section-table build --year 2026 \
  --bweb-root ~/data/election-audit-stage/inputs/resultados-2026-boletim-de-urna \
  --electorate-root ~/data/election-audit-stage/inputs/eleitorado-2026 \
  --semantic-r1 ~/data/election-audit-stage/phase20b-sessions/v4-national-r1-20261107 \
  --semantic-r2 ~/data/election-audit-stage/phase20b-sessions/v4-national-r2-20261107 \
  --integrity-r1 "$(cat ~/data/election-audit-stage/phase20b-sessions/integrity-v4c-r1.json)" \
  --integrity-r2 "$(cat ~/data/election-audit-stage/phase20b-sessions/integrity-v4c-r2.json)" \
  --exclusions data/national/phase11-protection-2026-10-31/exclusions.json \
  --output ~/data/election-audit-stage/phase20b-sessions/table-2026-v4-20261108c
```

`--integrity-r1`/`--integrity-r2` take a JSON object with the Phase 20 roots of the
round (`sections`, `logs`, `bweb`, `correspondence`). For 2022, omit the integrity
and exclusion options. The build runs in a single process with two DuckDB threads
and `--memory-limit` (1 GB by default). It holds rows in Python for one chunk at a
time: whole municipalities of one UF, about 10000 sections, because close rules
and units never cross a municipality. Nationally, version 3 took 47 and 78 minutes (2026, 2022) with a peak of 3.7 and 3.0 GB;
version 4 took 45 and 42 minutes with a peak of 3.7 and 3.1 GB, and each release is
about 190 MB. A first 2026 build on the Phase 20b logs v2
(`table-2026-v4-20261108b/`, 49 minutes) differs from the final one only in I5 and I7
of the 8 and 9 sections whose memory copies were counted twice. Unit tests:
`tests/test_section_table.py`.

## Development results

AC on 5 November 2026 (counts only):

| | 2026 r1 | 2026 r2 | 2022 r1 | 2022 r2 |
| --- | --- | --- | --- | --- |
| Sections | 2270 | 2270 | 2124 | 2124 |
| Results ready | 2270 | 2270 | 2124 | 2124 |
| Profile ready | 2270 | 2270 | 2124 | 2124 |
| Protected (logs unread) | 596 | 596 | 0 | 0 |
| Operations ready / partial | 1202 / 465 | 1317 / 346 | 1200 / 915 | 1401 / 718 |
| Clock `ok` / `adjusted` | 1666 / 1 | 1662 / 1 | 2115 / 0 | 2118 / 1 |

Every AC unit is `same_principal` and comparable in both years. Every AC urn that
printed a configured close printed 15:00 (52 sessions in 2026 round 2, 30 in 2022
round 2), which confirms that urn clocks run on local time.

## National results

Version 4, built on 8 November 2026 in
`~/data/election-audit-stage/phase20b-sessions/table-2026-v4-20261108c/` (on the
Phase 20b integrity sections v4 and logs v3) and `table-2022-v4-20261108b/` (counts
only; results and operational values stay unread):

| | 2026 r1 | 2026 r2 | 2022 r1 | 2022 r2 |
| --- | --- | --- | --- | --- |
| Sections | 499248 | 499248 | 472693 | 472693 |
| Results ready | 499206 | 499205 | 472028 | 472028 |
| Profile ready | 498858 | 498858 | 472349 | 472349 |
| With sessions / no official session / no log | 498568 / 12 / 72 | 498577 / 4 / 71 | 471844 / 15 / 834 | 471971 / 12 / 710 |
| Protected (logs unread) | 596 | 596 | 0 | 0 |
| Operations ready / partial / unavailable | 333365 / 165203 / 680 | 359069 / 139508 / 671 | 261283 / 210560 / 850 | 300549 / 171422 / 722 |
| Clock `ok` / `adjusted` | 495490 / 1451 | 495549 / 1651 | 469688 / 1202 | 469678 / 1439 |
| Clock `backstep` / `overlap` / `no_close_rule` | 34 / 24 / 0 | 9 / 7 / 0 | 23 / 60 / 0 | 4 / 15 / 0 |
| Log model agrees / differs with the BU | 498560 / 8 | 498577 / 0 | — | — |

Compared with version 3 (`~/data/election-audit-stage/phase22/table-2026-v3-20261107/`
and `table-2022-v3-20261106/`), only fields derived from the logs change. In 3069
sections (2026) and 1993 (2022) the round now has an official session: urns left on
overnight or restarted mid-day ([semantic pass](semantic-pass.md#version-4-phase-20b)).
Their log status, model, operations, clock and copy fields change with it. In 2026 the
I3 field changes in the two MG SA sections, and I5–I7 and I6 come from the Phase 20b
releases. Result and unit files are identical, as are close rules.

Every unit is `same_principal` in both years: 499248 units in 2026 (499205
comparable) and 472693 in 2022 (472028 comparable). The units that are not
comparable lack results in a round. Close rules, by section and year (both rounds
share them):

| Rule | 2026 | 2022 |
| --- | --- | --- |
| `law_uf` | 489730 | 464164 |
| `am_configured` | 8063 | 6752 |
| `am_list` | 94 | 704 |
| `abroad` | 1351 | 1064 |
| `law_noronha` | 10 | 9 |

Observations:

- Abroad (ZZ) accounts for 1211 of the 1451 round-1 `adjusted` clocks in 2026,
  and for every `backstep`.
- In 2026 round 2, 82 Mato Grosso sections are `adjusted`, against none in round
  1. Every one is an operator setting in ADH with a shift near −3600 s, in three
  municipalities, mostly in zone 0053
  ([observation O11](observations.md#operations)).
- In 2026 round 1, eight sections have a last-session log model that differs from
  the BU signer's model. In six, the signature file was signed by another urn
  ([observation O13](observations.md#operations)); two (RJ 60011/0214/0023 and 0024)
  used a reserve urn.
- The `am_list` sections (94 in 2026, 704 in 2022) are in municipalities whose urns
  printed no configured close in the year: no one tried to close early, so the
  close is taken from the list (2026: 32 at 15:00 and 62 at 16:00; 2022: 88 and
  616). Version 2 left them `unresolved`, and earlier versions of this page gave the
  wrong cause (more than one printed close). No printed close contradicts the list
  in either year.
- Version 3, compared with version 2: only Amazonas close rules and their clock and timing
  states change, plus, in 2026, the integrity fields of Phase 20b: `i1_signature`
  becomes `verified` for every Ed521 section and the urn type `reservaSecao` reads
  `contingenciaSecao`. Result and unit files are identical.

## Limits

- Block-start lineage identifies copies, and the longest copy is kept; copies that
  end at different lines (one section, [O16](observations.md#operations)) are not
  compared line by line.
- Completions after the close are counted in whole-hour bins. This is exact only
  because every legal closing time falls on the hour.
- The voter profile is a snapshot from before the election (July 2026, August
  2022). Sections created later have no profile and stay `unavailable`.
- Integrity status exists for 2026 only, because Phase 20 was not run for 2022.
