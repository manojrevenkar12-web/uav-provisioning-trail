# Working on this repository

## Fast feedback

- `pytest -q -m "not qemu and not db"`: seconds, no external tools.
- `pytest -q`: everything; needs `qemu-system-arm`, `arm-none-eabi-gcc` and PostgreSQL (`UAV_TEST_DATABASE_URL`).
- `ruff check src tests && ruff format --check src tests && mypy src`.
- `uavsim run campaigns/dev/shift-a.yaml && uavtrail evaluate data/runs/shift-a` (`UAV_DATABASE_URL` set).
- `cd web && npm run check`; `npx playwright test` against `uavtrail serve`.

## Invariants (each has a test)

- The station, server and analysis (`src/uavtrail`) never import `uavsim` and never read a campaign; only
  `src/uavtrail/evaluate.py` reads a run's `truth.json` (`tests/test_isolation.py`).
- Every write is read back before it counts (`tests/test_mcu_qemu.py`, `tests/test_orin.py`).
- Every step's intent is in the trail before it runs; the trail is append-only on the server
  (`tests/test_station.py`, `tests/test_server.py`).
- The fuse burn runs only when its guard finds nothing unmet (`tests/test_guards.py`, `tests/test_station.py`).
- Only signed releases with matching artifacts install (`tests/test_releases.py`).
- Every code a step raises is in `config/codes.yaml`; thresholds live in `config/`, not in code.
- Firmware layout and station layout agree (`tests/test_layout.py`).

## Held-out shifts

Never change the station or the analysis to pass a held-out set before its first run is recorded
(`reports/heldout/<set>/first_run.json`, never rewritten; CI checks it). If you study a set's failures to change
the analysis, write `regression` to `heldout/<set>/STATUS` and have someone who has not seen the code write a new
set from `heldout/WRITING_CAMPAIGNS.md` only.

## Where settings live

`config/targets.yaml` (flash layout, USB ids, EEPROM layout), `config/codes.yaml`, `config/recipes/`,
`config/line.yaml` (stations, fixtures, modelled durations), `config/analysis.yaml`, `config/instructions/`,
`releases/`. Environment: `UAV_DATABASE_URL`, `UAV_API_TOKENS`, `UAV_ROOT`, `UAV_DATA`, `UAV_WEB`.
