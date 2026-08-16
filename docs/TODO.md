# TODO — duration-aware detector rework

**Last updated:** 2026-08-16
**Plan:** `docs/plan-duration-aware-detector.md`

The fit side, table-backed count/duration serving, directional output, combined
regimes, persistence, plotting, and frontend presentation are complete in the
working tree. Dify integration remains user-owned and is intentionally out of scope.

---

## Completed and committed

- [x] Add the `m_roll_percentile_parameter` table in
  `mcp_conductor/entry/main_setup_schema.py`.
- [x] Use `(location_type, location_name, metric, valid_from_date_id)` as the parameter
  key, rather than overloading `pipe_name` for pipes and ports.
- [x] Document the parameter table in `CLAUDE.md`.
- [x] Add the fitting library in
  `mcp_conductor/detector/roll_percentile/fit.py`.
- [x] Add the fitting entry point and CLI in
  `mcp_conductor/entry/main_fit_model.py`.
- [x] Exclude zero metrics from fitting; for duration, also require `ship_cnt > 0`.
- [x] Fit each location with a 180-record training-plus-validation budget and record
  the actual `fit_start_date_id` / `fit_end_date_id` span. Training is positive-only;
  ship-count validation retains zeros.
- [x] Assign `OK`, `FLAT`, `INSUFFICIENT`, or `NO_DATA` at fit time and leave bounds
  NULL for non-OK fits.
- [x] Support versioned, idempotent parameter persistence.
- [x] Respect `is_locked` rows during refitting.
- [x] Populate the live parameter table. After canal cleanup and zero-aware validation,
  58 rows are effective: 50 `OK` and 8 `INSUFFICIENT`.
- [x] Fix BCI sync validation so one malformed item does not discard valid sibling
  items; still fail a day when every item is malformed.

Useful fit commands:

```bash
uv run python mcp_conductor/entry/main_fit_model.py --dry_run
uv run python mcp_conductor/entry/main_fit_model.py
```

---

## Completed and committed — table-backed serving

- [x] Remove the hardcoded Hormuz branch from
  `mcp_conductor/detector/roll_percentile/rolling_percentile.py`.
- [x] Set the current Hormuz `ship_cnt` parameter bounds to `[15, 25]`.
- [x] Look up the parameter row effective for the location, metric, and detection
  date in `mcp_conductor/detector/detect_engine.py`.
- [x] Pass the effective parameter row into `RollingPercentileDetector.detect()`.
- [x] Use stored lower/upper bounds, anomaly threshold, and interval instead of
  calculating percentiles from the serving window.
- [x] Short-circuit detection when no effective parameter row exists or its status is
  not `OK`.
- [x] Add focused tests for effective-date lookup and table-backed detection.
- [x] Replace the skipped/live-database engine tests with hermetic pipe and port
  coverage.
- [x] Verify focused tests: 11 passed, 0 skipped on 2026-08-08.
- [x] Review and commit the modified detector and detector-test files in commit
  `58bdab5`.

---

## Immediate work — completed in the working tree

- [x] Store the Hormuz `[15, 25]` `ship_cnt` row as `fit_method='manual'` with
  `is_locked=1` so a refit cannot overwrite it.
- [x] Move `mcp_conductor/detector/generic/rolling_percentile.py` into
  `mcp_conductor/detector/roll_percentile/` and update imports and test paths.
- [x] Add unit tests for `fit_one_location()` covering zero filtering, recent-N,
  statuses, ship-count gates, and duration gates.
- [x] Add persistence tests covering versioning, identical-fit idempotency, and
  locked-row protection.
- [x] Add tests for `main_fit_model.py` orchestration and dry-run behaviour.
- [x] Restore `docs/plan-duration-aware-detector.md`.

---

## Directional count output — completed in the working tree

- [x] Split `anomaly_ratio` into `ratio_high` and `ratio_low` while retaining the
  combined value as a compatibility field.
- [x] Emit anomaly direction so a traffic surge and a traffic collapse do not produce
  byte-identical result rows.
- [x] Persist direction and directional ratios with an idempotent schema migration.
- [x] Update API responses, analysis prompts, and Dify workflow fields to use direction.
- [x] Define exact ties as `MIXED`, non-anomalous results as `NORMAL`, and unusable
  results as `UNKNOWN`.

## Detection and reporting work — completed in the working tree

- [x] Add the fitted duration channel to `detect()`; duration parameter rows already
  exist.
- [x] Define the combined count/duration regime matrix, including outcomes such as
  `AVOIDANCE` and `BLOCKAGE`.
- [x] Widen `m_pipe_anomaly_roll_percentile` to store duration results.
- [x] Add `location_type` to the anomaly-result primary key so same-name pipes and
  ports cannot overwrite each other; migrate legacy rows and update all consumers.
- [x] Update plots to display direction and duration anomalies.
- [x] Update the frontend for the widened detector output.

---

## Open data and calibration issues

### Sparse locations cross possible regime breaks

- [x] Define and apply location-specific `fit_start` floors. Production fitting now
  floors 南沙港, 阿布扎比港, 杰贝阿里, and 德班港 at `20260101`.

The worst observed fitting spans start at 南沙港 `20231108`, 阿布扎比港 `20240507`,
杰贝阿里 `20240618`, and 德班港 `20240713`. Recent-N controls sample size but can
still reach back across a regime change. These locations have fragmented coverage
after July 2024 and sustained current-era coverage resumes in January 2026. The floor
retains 91–161 usable observations per location as of July 2026. A later explicit
`--fit_start` remains stricter; the production floor is ignored for historical
`--as_of` dates before the floor.

### Canals duplicated as ports

- [x] Add a sync exclusion so `巴拿马运河` and `苏伊士运河` cannot be written to
  `ship_cnt_in_port`, even when the upstream API returns them under port metric
  `zbxx` values `101-0001` or `101-0002`.
- [x] Delete the existing 1,529 `ship_cnt_in_port` rows for each canal after taking a
  database backup.
- [x] Delete the four invalid `m_roll_percentile_parameter` rows where
  `location_type='port'` and `location_name` is `巴拿马运河` or `苏伊士运河`.
- [x] Add a sync regression test proving that canal names are retained for pipe
  metrics but rejected for port metrics.
- [x] Refit parameters and rerun directional detection after cleanup.

Confirmed on 2026-08-09:

- These are the only names shared by `ship_cnt_in_pipe` and `ship_cnt_in_port`.
- Each has 1,529 erroneous port rows spanning `20220101` through `20260422`.
- Every erroneous port row has `duration IS NULL`.
- On shared dates, the port ship-count values almost exactly duplicate the pipe
  series: 991 of 994 comparable Panama rows and 986 of 989 comparable Suez rows are
  identical.
- Before cleanup, sync routed solely by each item's `zbxx`; the new pipe-only guard
  rejects these canal names when upstream returns them under a port metric.
- Keep the canal rows and fitted parameters where `location_type='pipe'`; only the
  invalid port data and port parameters should be removed.
- Cleanup completed on 2026-08-15 after backing up
  `data/backups/sisi-before-canal-cleanup-holdout-20260815.sqlite`. Exactly 3,058
  invalid observations and four invalid parameter rows were removed; both valid pipe
  series retain 1,109 observations.

### Chronological holdout calibration

- [x] Add a chronological holdout split to `_derive_threshold()`.
- [x] Revalidate per-location thresholds and the target live flag rate after the
  holdout change.

The latest 30 scoring observations are reserved for calibration. Ship-count
validation retains zeros because zero traffic is a low-side signal; normal bounds
still use positive training observations only. Duration validation continues to
exclude unusable observations, matching serving. Rolling validation windows are
seeded by the preceding 29 scoring observations. Calibration provenance and realized
flag rate are persisted with each parameter row.

The zero-aware `20260725` refit produced 27 automated `ship_cnt` fits and 22 duration
fits with status `OK`, eight `INSUFFICIENT` fits, and one locked manual count row.
Count thresholds span `0.20–0.767`; the mean validation flag rate is 17.28% and the
maximum is 73.33% because zero-count days and the latest-zero rule are intentionally
anomalous. Duration thresholds span `0.20–0.60`, with a 2.42% mean and 6.67% maximum
validation flag rate. Rerunning `20260726` detection produced 25 normal count results,
three low-count anomalies, and one unusable count result.

### Corrected-threshold live monitoring

- [x] Add an idempotent `m_roll_percentile_monitor` snapshot table.
- [x] Calculate `ANY`, `LOW`, `HIGH`, and `MIXED` rates by location and metric.
- [x] Exclude results produced before the currently effective parameter version.
- [x] Exclude unusable count/duration outcomes from eligible denominators.
- [x] Run monitoring automatically after detection and provide a standalone dry-run
  CLI.

The default monitor requests 30 calendar days and waits for 30 eligible results before
alerting. Its default alert boundary is `max(10%, 2 × calibration_target_flag_rate)`.
The first `20260726` snapshot contains 232 direction rows across 58 effective
location/metric parameters: 200 are `WARMING_UP`, 32 reflect eight unusable parameters,
and none are elevated yet.

---

## Verification status

- [x] Directional detector, schema, persistence, and API tests pass: 39 passed,
  0 skipped on 2026-08-09.
- [x] Live-data fitting smoke test passes in `--dry_run` mode.
- [x] Full `uv run pytest tests/` result: 86 passed, 3 skipped on 2026-08-09.
- [x] Duration/regime detector, schema, persistence, and plot tests pass: 41 passed,
  0 skipped on 2026-08-15.
- [x] Full `uv run pytest tests/` result: 90 passed, 3 skipped on 2026-08-15.
- [x] Next.js production build passes on 2026-08-15.
- [x] Canal sync, holdout fitting, CLI, schema migration, and persistence tests pass:
  23 passed on 2026-08-15.
- [x] Live cleanup, holdout refit, 2026-07-26 detection rerun, and SQLite integrity
  verification completed on 2026-08-15.
- [x] Monitoring schema, aggregation, CLI, automatic detection hook, and persistence
  tests pass: 9 passed on 2026-08-15.
- [x] Zero-aware count validation and serving-alignment tests pass; detector and entry
  suites pass: 67 passed, 1 skipped on 2026-08-15.
- [x] Location-type result migration preserved all 14,020 historical rows: 11,520 pipe
  and 2,500 port. Duplicate-name persistence, monitoring, migration, and consumer
  tests pass; detector, entry, and focused API SQL suites pass: 73 passed, 1 skipped
  on 2026-08-16. The frontend production build also passes.

Always scope pytest to `tests/`; bare pytest also collects the vendored `dify/` tree.
