# Phase 15 — Frozen research protocol and final-evaluation protection

Document-ID: EA-HANDOFF-15 · Revision: 1 · Language: en

Prerequisites: the approved completion plan and phase 14 feature releases. This new research scope authorizes model fitting in later phases without changing foundation release semantics.

Implemented: `research_protocol.py` verifies the feature-catalog pin, streams units into a frozen SQLite partition catalogue, groups reviewed stable locations across rounds, reserves municipal stress populations and preserves unavailable identity/source states. A persistent anchored inspection registry excludes reviewed locations after reseeding. The source and partition populations are checksummed; no outcome values enter partition selection.

`research_evaluation.py` provides a separate append-only execution journal with immutable record IDs and references, a hash chain, exact final-access/evaluation unit ledgers, one-use final evaluation, and atomic frozen journal snapshots. A final marker requires a completed fitted model, matching protocol/partition/model references and the exact protected population. Mere test inspection and forged legacy marker rows do not unlock dashboard exports. Source partitions are checked against their original hash when validating a final proof. Existing v1 ledgers and releases are preserved.

Interfaces: `publish_protocol(feature_release, output, inspected=None, seed=42)`, `load_protocol`, `record_inspection`; `open_journal`, `append_record`, `record_evaluation_units`, `record_final_evaluation`, `snapshot_journal`, and `final_evaluation_complete(db, document=None)`. The CLI adapter is `research_protocol_main`. All record payloads carry `protocol_id` and `partition_id`. Fitted model records require `fitted=true`, `state=complete`; final access and evaluation records require `model_run_id`, `stage=final`, `state=complete`. Journal callers commit transactions explicitly. Immutable protocol directories never contain the mutable execution journal.

Acceptance: six regression tests pass, covering grouped assignments, unavailable units, cross-geography identity conflicts, inspection persistence across seeds, source-pin corruption, exact final populations, one-use access/evaluation, immutable records, tampered hash chains/partitions and fail-closed legacy dashboard behavior. Ruff checks and formatting pass.

Actual AC protocol: `data/phase15/ac-protocol` consumes the 2270 eligible units in `data/phase14/ac-location-development`. Partition counts are training 1259, calibration 399, protected test 340, municipal stress 256 and development_inspected 16. The three reviewed binary-BU pilot locations were recorded with preserved source anchors in `data/phase15/inspection.sqlite`; all 16 units at those locations remain development data. Protocol ID: `9128a902f94868ac0a453b199b02f37b028c5383bf9800ae8010d6bf70b2b869`; partition ID: `ca136d404aaa98eff2c0968f7ddf068a92b0f379f6be84e026e77da7d3e48d67`.

Limits: this is an AC second-round development/evaluation population with same-round official location grouping. No cross-round identity or national analysis is claimed. Missing first-round covariates require the no-first-round model variant. No model or final evaluation was run by phase 15. External manual inspection cannot be prevented by a local notebook: such access must be recorded. New aliases or merged locations must propagate the inspection registry before new partitions are frozen.

Next: phase 16 fits on the eligible training population, calibrates separately, records final access once, evaluates the exact protected population (including explicit unavailable outcomes), and freezes a journal snapshot. A completed snapshot remains conditional research evidence, never a fraud certificate.
