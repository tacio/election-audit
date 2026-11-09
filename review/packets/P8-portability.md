# Packet P8: reproducibility on another machine

A stated objective of this project is that someone else, on their own machine, can
install it, run it and reproduce its results. This packet tests that objective, both by
hand and by reading.

Scope:

- `README.md`, `pyproject.toml`, `uv.lock`, `justfile`
- `docs/en/reproduction.md`, `docs/en/backfill.md`, `docs/en/snapshots.md`
- `election_audit/reproduction.py`, `pilot.py`, `walkthrough.py`, `cli.py` (`doctor`)
- Every documented command that an outsider would run.

## Hands-on

Act as a newcomer with a fresh machine, using only what the README and
`docs/en/reproduction.md` say.

1. Ignore the prepared `.venv`. Build your own environment from the lock:
   `UV_OFFLINE=1 UV_PROJECT_ENVIRONMENT=review-scratch/venv uv sync --locked`. The
   network is off, but the package cache is available offline.
2. Follow the README quick start literally: `doctor`, the gate, the synthetic `demo`,
   then `review-bundle` and `reproduce` on the demo output. Write every output under
   `review-scratch/`.
3. For each step, record:
   - whether it worked as written;
   - what you had to change or guess;
   - what knowledge the docs assumed but did not give.

A step that fails only because the network is off is reported as "needs network", not
as a failure.

## Press on

- Required tools beyond Python and uv: `just` and `rtk`. Is each one necessary? Every
  recipe wraps itself in `rtk proxy`, and `rtk` condenses output for AI agents. Can an
  outsider run the project without it, and do the docs say how?
- Operating-system assumptions: Linux-only interfaces (`/proc`, FIEMAP), `resource`,
  file-system features, case sensitivity and path separators. What happens on macOS,
  Windows or WSL: a clear refusal, a silent difference, or a crash?
- Machine-specific values in code or in documented commands: user names, home paths,
  mount points, staging folders.
- Hardware assumptions: RAM, CPU count, SSD versus HDD, and disk space for the national
  runs. Are they stated with numbers? Can a smaller machine reproduce a subset, such as
  one state, and is that documented?
- Inputs an outsider cannot fetch with the tooling: files downloaded by hand in a
  browser, frozen inputs that are not redistributed, and sources that may move or
  vanish. Does each have enough provenance (URL, date, hash) to be obtained again and
  checked?
- Determinism across machines: float summation, thread counts, locale, time zone, sort
  stability, and DuckDB and Arrow versions. Would another machine produce the same
  release digests? Where do the docs promise identical bytes, and where do they promise
  only equal values?
- The Python 3.14 requirement and the lock: does `uv.lock` resolve on other platforms
  and architectures?
