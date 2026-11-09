# Campaign xr1-20261109: notes

- Pinned commit: 1801029bdc0434a94ddf6670a1014f2d284df452.
- Pilot (R1, packets P3, P7 and P8), 10:17 to 11:01 on 9 November 2026. The runner did
  not pass models yet, so `model` is null in `runs.jsonl` for these six sessions. The
  models were the CLI defaults, confirmed from the CLI config and log:
  - Codex: `gpt-6.1-sol`, at reasoning effort `high` (passed by the runner).
  - Gemini: `gemini-3.8-flash-high` (Antigravity CLI). Pro is not offered on this
    plan.

  From then on the runner pins both models, and each lane refuses another provider's
  model.
- Gemini, P8 (first attempt): asked to run `election-audit demo` outside its sandbox.
  Print mode denied it. The session then ended with an empty answer, so it produced no
  report. The R1 prompt gained one line before the rerun: "Never ask to run a command
  outside your sandbox." Pilot sessions ran with the earlier prompt (see
  `prompt_sha256`).
- Boundary flags in the pilot are false positives:
  - Codex P8 searched the clone for hard-coded paths, which is its task.
  - Gemini P7's flag matched a DOI link in the final report's text. The audit no longer
    scans final reports.
