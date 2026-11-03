# Statistical analysis foundation

Document-ID: EA-ANALYSIS · Revision: 3 · Language: en

[Português](../pt-BR/analysis.md) · [Index](implementation-index.md) · [Electoral parent](electoral-results.md)

Phase 8 publishes descriptive foundations from an immutable operational or electoral derivative release. It fits no model and applies no automatic fraud labels. Any UF subset, including the default AC–RJ snapshot, is partial national coverage. Every numeric feature retains its source-quality blockers (final totalization linkage, complete choice evidence and independent final references are still unavailable), unknown temporal availability and unavailable scientific eligibility. No exchangeability or coherent final national margin is asserted. Model fitting happens only in the later research path (`features`, `research_protocol`, `research_models`, `investigations`; Phases 14–17), documented in its handoffs.

Use a local explicit configuration, at most 8 MiB. The optional candidate_a/candidate_b fields must be distinct official contest-scoped candidacy IDs fixed together; neither is inferred. Empty links preserve every unknown location as ineligible. Configuration bytes are preserved and pinned in the new child.

```json
{
  "version": "audit-analysis-v1",
  "cutoff_at": "2026-10-29T00:00:00+00:00",
  "partition": {
    "version": "location-partition-v1",
    "seed": "reviewed-protocol-v1",
    "fractions": {"training": 0.6, "calibration": 0.2, "test": 0.2},
    "links": [],
    "municipal_holdout": []
  },
  "records": []
}
```

```sh
rtk proxy env UV_OFFLINE=1 just analyze /ssd/audit/releases/PARENT_DIGEST --bundle /ssd/design/analysis.json --store /ssd/audit
rtk proxy env UV_OFFLINE=1 just validate /ssd/audit
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT partition_id, payload FROM partition_plan'
rtk proxy env UV_OFFLINE=1 just query /ssd/audit --sql 'SELECT feature_id, count(*) FROM training_features GROUP BY feature_id'
rtk proxy env UV_OFFLINE=1 just report /ssd/audit --output /ssd/reports --language both
```

`analysis.publish_analysis(parent, bundle, store, config=None)` uses the existing lock, resource limits, staging/fsync/rename/current-pointer transaction and relative checked parent chain. Parent operational facts are reused, never copied or rewritten. The long `audit_features` ledger streams bounded batches from SQL. Compact link populations, evidence catalogues and inherited/current analysis records are bounded by max_events; this is a foundation, not a national streaming model trainer. Failed publication leaves the previous current artifact intact; identical calls resume. Preserve the full relative parent chain on relocation.

All 21 contracts appear in `audit_feature_registry`, with exact required inputs, definitions, components, source tables, units, numerator/denominator descriptions, temporal rule, roles, specifications and blockers. Each expected principal and unresolved frozen section retains rows in `audit_features`; every value has its parent/source keys, transformation version, numerator, denominator, cutoff and quality indicators. Turnout, separate blank/null shares and symmetric A/(A+B), B/(A+B) can be computed from complete reconciled normalized counts; electorate is descriptive context. Missing/zero denominators and unresolved A/B/categories remain unavailable. Other requested operational, temporal, historical, integrity, inferential and counterfactual components explicitly name their blockers and source marts. No first-round baseline is presumed available.

The operational_adjusted specification treats device/model/version/logistics as possible adjustments; mechanism retains them as possible mechanisms. no_first_round uses current-cycle-only context; history_assisted requires comparable history. Turnout, manual authorization and outages are never automatic controls. Source availability dates currently remain unknown, preventing predictive eligibility even when retrospective numeric arithmetic is available.

Partitions require reviewed stable polling-location links across related observations, including rounds and history. Same school name, section code or election-scoped location ID never establishes stable identity. A link has exactly these fields; replace the illustrative digest with an actual frozen source_object hash. Publication rejects anchors that do not resolve to the checked parent catalogue. Record locators and verified=true express supplied review assertions; byte integrity does not independently certify the asserted identity.

```json
{
  "location_id": "election-scoped-id",
  "stable_location_id": "reviewed-cross-round-id",
  "verified": true,
  "evidence": {
    "object_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "record_locator": "exact preserved register/review record locator"
  }
}
```

`partition_plan` pins exact sorted population/hash, seed/version, fractions, geographic UF/municipality strata, original link anchors, assignment rule and municipal holdout list (UF:municipality_tse). `location_partition` preserves every observation. A stable location receives one SHA256 probability-threshold assignment within its stratum, so small strata need not realize exact fractions. All related observations stay together. Unknown identity remains unavailable, with no guessed fallback. Municipality stress designations hold out complete municipalities. Population/seed/version changes create new partition IDs; stale/conflicting links and published assignments fail. Plans and assignments append without modifying prior releases.

First publish the partition, read its exact partition_id, then publish a child carrying records. Every record uses the exact versioned envelope below; immutable record_id conflicts fail, identical retransmissions deduplicate, and new versions use new IDs. Generic and typed references are validated before atomic publication. The API accepts records in any input order.

```json
{
  "record_id": "protocol-v1",
  "version": "analysis-ledger-v1",
  "record_kind": "protocol",
  "analysis_run_id": null,
  "created_at": "2026-10-29T00:00:00+00:00",
  "references": [],
  "payload": {
    "state": "frozen",
    "question": "conditional_unusualness",
    "partition_id": "replace-with-persisted-partition-id",
    "family": [{
      "outcome": "turnout",
      "subgroup": "all",
      "window": "election_day",
      "scale": "location",
      "model_variant": "no_first_round",
      "historical_comparison": "none"
    }]
  }
}
```

`analysis_ledger` kinds: protocol freezes or marks exploratory every outcome/subgroup/window/scale/model/history family; analysis_run pins protocol, snapshots, source configuration and model config IDs; model_config stores estimator/hyperparameters/seeds with fitted=false; exploration retains family status, result and null_result; analysis_snapshot lists the exploration history and cannot mark complete while omitting a registered family member or an explored/null result. The supplied history attests recorded work; the pipeline cannot discover unreported external searches.

calibration records exact persisted calibration location population, n_cal, score configuration and unvalidated assumptions. Unknown/test/training units cannot enter that calibration population. score records a finite descriptive score, matching configuration and calibration references, and a known unit; interpretation must be descriptive_only. No fitted scores, valid fraud p-values or FDR guarantees are produced. investigation retains score/unit references, alternative explanations, independent corroboration, candidate-blinding status and an unresolved/benign/requires-review conclusion. Automatic fraud conclusions are rejected. Original evidence anchors must resolve to frozen objects.

Untouched test outcomes are reserved by the query interface. Metadata and `training_features` remain queryable; the latter includes linked training/calibration units and excludes any location reserved by an untouched test population. Other outcome-table queries and dynamic table functions are blocked while any test location is untouched. Publish a test_access record with the matching run/protocol/partition, purpose and inspection=true before inspection. `test_partition_status` then marks those stable locations development_inspected for future analyses, including later seeds/populations. A future frozen protocol cannot recycle an inspected test location. Internal release loaders support validation; using them to inspect outcomes also requires recording access. Aggregate availability reports reveal no individual test outcomes.

impact records require one exact snapshot/election/contest and distinct candidate IDs, an explicit mechanism (removal_exact/removal_at_most/switching_cap), affected principal populations, completed-ballot caps and source anchors, overlap handling, final_margin and margin_assumptions. Published counts must match the pinned normalized canonical target; this is not independent real BU validation. Counts from different rounds/contests cannot be summed. Only disjoint principals or a corroborated deduplicated union per principal are summed. Overlap, missing margin or unsupported caps stays unavailable. Anonymous subset choices remain unknown. Bounds are conditional arithmetic under the stated margin/mechanism; they do not establish stolen votes, candidate attribution, causal effects or a national confidence interval. A tied assumed margin requires one switch for a strict win. The pure helper accepts explicit count assumptions; the publisher adds source/target validation.

Reports default to en and pt-BR, share identical calculations in findings.json, and include feature availability, partition/access summaries, ledger counts, conditional scenario bounds, exact SQL, configuration, validation and complete parent-chain file/table pins. `--language en|pt-BR|both` changes human labels only. Reports must be outside every immutable parent and child.

The research path builds on these ledgers: Phase 14 publishes feature releases, Phase 15 freezes protocols and the protected final-evaluation journal, Phase 16 fits models and Phase 17 builds investigation packets. See their [handoffs](implementation-index.md#phase-status). Acceptance of this foundation does not authorize model fitting or fraud labeling.
