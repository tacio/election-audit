# Phase 16 — Conditional models and protected evaluation

Document-ID: EA-HANDOFF-16 · Revision: 1 · Language: en

[Português](../../pt-BR/handoffs/task-16.md)

Implemented `research_models.py`: bounded compact feature matrices, sparse training with 64-row dense prediction blocks for the pinned forest library, training-only geographic three-fold CV, electorate-matched empirical baselines and quantile forests. Defaults: 256 trees, depth 24, leaves 25/100, four workers, seed 42; target/variant and source/catalog/protocol identities are pinned. Artifacts contain model and configuration hashes, calibration diagnostics, signed residuals and descriptive tail ranks. Final access uses the separate Phase 15 journal; the actual AC run has not accessed test outcomes.

Real AC development fit: `data/phase16/ac-turnout`, 1259 training and 399 calibration units; forest selected with leaf 25. Calibration quantile loss 0.013169431860532732 versus baseline 0.015507040245676146; nominal 95% interval coverage 0.9448621553884712. These are retrospective development diagnostics, not final evaluation or fraud evidence. Calibration predictions: `data/phase16/ac-turnout-development`.

Validation: four tests pass, covering reproducible fitted configurations/metrics, train/test separation, immutable source pins, one-use final evaluation, model corruption, count caps, sanitized history injection and resumed callback identity. Ruff passes. `run_mechanism_validation` supplies reconciled-ballot and sanitized-history perturbations to a pinned full-fit/calibrate/score callback, with per-seed SQLite checkpoints. Its caller must supply the complete estimator pipeline; callback test results are not claimed as measured detector power. The CLI `simulate` is separately labeled feature-perturbation sensitivity without refitting and must not be reported as ballot-mechanism validation.

Remaining: complete the frozen multi-target/variant family, concrete end-to-end mechanism/refit validation on real source-derived validation copies, final held-out evaluation, national processing and any defensible inferential assumptions. Operational targets require eligible event-derived features. Unsupported variants/targets fail with explicit missing-input messages. No automatic fraud labels, certified p-values, FDR claim or causal effect. Next phase: 17 investigation consumes the hashed development predictions and phase 15 partition registry.
