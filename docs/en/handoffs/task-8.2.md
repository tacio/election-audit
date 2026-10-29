# Task 8.2 — Frozen stable-location partitions

Document-ID: EA-HANDOFF-8.2 · Revision: 1 · Language: en

Objective: persist exact populations, seeds, geographic strata and training/calibration/test assignments. `analysis_partitions.assign_partitions` and `partition_tables` require verified cross-round stable-location links with original-record anchors. Same section code, election-scoped location ID or school name alone never supplies identity. Unknown links retain ineligible rows.

Artifacts: `partition_plan` pins sorted exact unit population hash, fractions, seed/version, links and rule; `location_partition` preserves every observation and identity evidence. SHA256 thresholds operate within UF/municipality strata; small strata need not realize exact requested counts. A municipal stress list holds out entire municipalities. Population/seed/version changes create new identities; parent artifacts are immutable.

Acceptance: three focused partition tests passed (exit 0): verified cross-round grouping/no overlap/unknowns; order/resume stability, changed seed/population and municipal stress; stale/conflicting/unverified links, geography and fraction errors rejected. Persisted derivative/report integration is included in task 8.3 final checks.

Next: task 8.3, immutable protocol/exploration/investigation records, conditional scenarios and test access history. Partition identity is an evidenced assertion, not independently certified real-corpus linkage. No real data or acquisition reads.
