# Plan — duration-aware rolling-percentile detector

**Last updated:** 2026-08-16
**Status:** Fit/serve split, chronological holdout calibration, cleaned canal routing,
table-backed count/duration serving, directional output, regime classification,
persistence, plotting, and frontend presentation are complete in the working tree.
Dify integration is user-owned and intentionally out of scope.

## Objective

Make rolling-percentile anomaly detection reproducible and duration-aware.

The detector must score observations using versioned parameters fitted before the
serving date. It must eventually distinguish high traffic from low traffic and
combine traffic counts with transit or berth duration so downstream consumers can
differentiate congestion, blockage, avoidance, and ordinary variation.

## Why the detector is changing

The original implementation calculated percentiles from the trailing history every
time `detect()` ran. That caused three problems:

1. The window being scored influenced its own definition of normal.
2. Re-running an old date could produce a different answer as source history changed.
3. A single anomaly ratio did not distinguish unusually high traffic from unusually
   low traffic.

Ship count alone is also ambiguous. A low count can represent avoidance, closure, a
source-data gap, or ordinary low demand. Duration provides a second signal that can
help distinguish these cases.

## Data observations behind the design

- Zero metrics are not useful fitting observations. In particular, duration is
  generally zero when there were no ships to measure; treating those rows as genuine
  durations pins the lower percentile at zero.
- Locations have very different activity levels. A shared calendar window yields
  enough samples for busy locations but too few for sparse ones.
- Using a 180-record budget gives a consistent sample size. The newest 30 scoring
  observations are reserved for validation; the remaining budget is filled with
  positive training observations. Recording the actual date span makes unusually
  long lookbacks visible.
- Duration reliability depends on the number of ships contributing to the daily
  average. Locations with a median of fewer than three ships per usable day should
  not receive duration bounds.
- Threshold calibration uses a chronological holdout so the observations used to
  evaluate the threshold cannot influence the fitted percentile bounds.

## Target architecture

```text
source observations
        |
        v
scheduled/offline fit
        |
        v
versioned m_roll_percentile_parameter rows
        |
        v
date-effective lookup -> count and duration scoring -> direction/regime
        |
        v
stored anomaly result -> API/prompts -> plots/frontend
```

Fitting owns historical-data gates, percentile bounds, and threshold calibration.
Serving owns effective-date lookup and scoring only; it must never recalculate bounds
from the observations being scored.

## Parameter schema

`m_roll_percentile_parameter` is keyed by:

```text
(location_type, location_name, metric, valid_from_date_id)
```

Important columns:

- `valid_from_date_id` / `valid_to_date_id`: inclusive effective-date range; NULL
  `valid_to_date_id` means currently in force.
- `lower_bound` / `upper_bound`: fitted or manual scoring band; NULL for non-OK rows.
- `anomaly_threshold`: location-specific out-of-band ratio threshold.
- `interval_days`: scoring window associated with that threshold.
- `status`: `OK`, `FLAT`, `INSUFFICIENT`, or `NO_DATA`.
- `fit_method`: currently `percentile_10_90_holdout` or `manual`.
- `fit_start_date_id` / `fit_end_date_id` / `fit_sample_size`: fitting provenance.
- `training_sample_size`: earlier observations used to fit percentile bounds.
- `calibration_start_date_id` / `calibration_end_date_id` /
  `calibration_sample_size`: chronological holdout provenance.
- `calibration_target_flag_rate` / `calibration_flag_rate`: requested and realized
  holdout flag rates.
- `is_locked`: prevents scheduled fitting from replacing a manual override.

Only one row should be effective for a location type, location name, metric, and
serving date. A new fit closes the previous row at `valid_from - 1`. Repeating the
same fit date updates the same row rather than creating a duplicate.

## Fit contract

The fitting implementation lives in
`mcp_conductor/detector/roll_percentile/fit.py` and is orchestrated by
`mcp_conductor/entry/main_fit_model.py`.

For each location and metric:

1. Load observations through `as_of_date_id`, optionally bounded by `fit_start`.
2. Reserve the latest 30 scoring observations as chronological validation data.
   Ship-count validation includes zeros; duration validation excludes missing or
   non-positive observations and rows without contributing ships.
3. Fill the remaining `recent_records` budget, defaulting to 180 total records, with
   the latest positive training observations. Duration training also requires
   `ship_cnt > 0`.
4. Require at least 60 positive training observations.
5. Calculate the 10th and 90th percentiles from training observations only.
6. Reject equal bounds as `FLAT`.
7. Reject ship-count upper bounds at or below three as `INSUFFICIENT`.
8. Reject duration fits whose median contributing ship count is below three.
9. Freeze the bounds, score rolling windows ending in the validation block, including
   zero ship counts as low-side observations, and derive the threshold from that ratio
   distribution.
10. Persist the versioned parameters and calibration provenance unless the current
    row is locked.

`fit_one_location()` remains a pure DataFrame-to-dict function so the fit rules can
be tested independently of database persistence.

## Serve contract

For the requested serving date, location, and metric:

1. Load the single parameter row effective on that date.
2. Return `NO_DATA` when no effective row exists.
3. Map non-OK fit statuses to their detector flags without scoring observations.
4. Use the stored bounds, interval, and anomaly threshold.
5. Score only the most recent configured interval.
6. Count observations below and above the stored bounds separately.
7. Preserve `anomaly_ratio` and the latest-zero sentinel for compatibility while new
   consumers use `ratio_low`, `ratio_high`, and `direction`.

Serving scores `ship_cnt` and `duration` independently. Direction is `NORMAL` when the
combined outlier ratio does not exceed the metric's threshold, otherwise the dominant
side is `LOW` or `HIGH`; an exact anomalous tie is `MIXED`. Missing or unusable data is
`UNKNOWN`. Duration ignores missing/non-positive observations and rows with no
contributing ships, matching its fitting series. The legacy count quantile and
combined-ratio output columns remain for compatibility.

The combined regime matrix is fixed as follows. Rows are ship-count direction and
columns are duration direction:

| Count \ Duration | `NORMAL` | `LOW` | `HIGH` | `MIXED` | `UNKNOWN` |
|---|---|---|---|---|---|
| `NORMAL` | `NORMAL` | `FAST_TRANSIT` | `DELAY` | `VOLATILE` | `COUNT_NORMAL` |
| `LOW` | `LOW_TRAFFIC` | `AVOIDANCE` | `BLOCKAGE` | `VOLATILE` | `LOW_TRAFFIC` |
| `HIGH` | `TRAFFIC_SURGE` | `HIGH_THROUGHPUT` | `CONGESTION` | `VOLATILE` | `TRAFFIC_SURGE` |
| `MIXED` | `VOLATILE` | `VOLATILE` | `VOLATILE` | `VOLATILE` | `VOLATILE` |
| `UNKNOWN` | `DURATION_NORMAL` | `FAST_TRANSIT` | `DELAY` | `VOLATILE` | `UNKNOWN` |

## Delivery phases

### Phase 1 — parameter fitting and storage

- [x] Create the versioned parameter table.
- [x] Implement pure fitting rules and threshold derivation.
- [x] Implement idempotent persistence and locked overrides.
- [x] Add fitting CLI and populate count/duration parameter rows.
- [x] Add unit and persistence tests.

### Phase 2 — table-backed ship-count serving

- [x] Load the row effective on the serving date.
- [x] Remove per-run percentile calculation and the Hormuz code branch.
- [x] Use stored bounds, interval, threshold, and status.
- [x] Move the detector into the `roll_percentile` package.
- [x] Lock the Hormuz `[15,25]` manual override.

### Phase 3 — directional count output

- [x] Count observations below the lower bound separately from observations above the
  upper bound.
- [x] Persist `ratio_low` and `ratio_high`.
- [x] Define and emit `NORMAL`, `LOW`, `HIGH`, `MIXED`, and `UNKNOWN` directions with
  explicit tie behaviour.
- [x] Migrate API and prompt consumers to the directional ratios while retaining the
  legacy combined ratio in the API response.
- [x] Add an idempotent SQLite migration for existing anomaly result tables and views.

### Phase 4 — duration serving

- [x] Load the effective duration parameter row alongside the ship-count row.
- [x] Score duration with its stored interval, bounds, threshold, and status.
- [x] Define missing-duration behaviour independently from missing ship-count data.
- [x] Persist duration ratios, direction, and status.

### Phase 5 — regime and presentation

- [x] Define the count/duration regime matrix and names.
- [x] Widen the anomaly result schema without breaking existing reads.
- [x] Key anomaly results by `(location_type, pipe_name, date_id)` so same-name pipe
  and port results remain independent.
- [x] Update plots and frontend presentation.
- [x] Leave historical duration/regime columns NULL until detection is rerun, making
  pre-duration rows explicit without inventing backfilled classifications.

Dify prompts, workflows, and API integration are user-owned and are not part of this
implementation phase.

### Phase 6 — calibration and data quality

- [x] Add chronological holdout/rolling-origin threshold calibration.
- [x] Apply a `20260101` production `fit_start` floor to sparse ports 南沙港,
  阿布扎比港, 杰贝阿里, and 德班港. Explicit later floors win, while historical
  as-of fits before the boundary remain available.
- [x] Reject Panama and Suez port metrics during sync, remove the 3,058 existing
  invalid port observations and four port parameter rows after backup, refit, and
  rerun detection.
- [x] Monitor live flag rates by location, metric, and direction. Each detection run
  now upserts `ANY`, `LOW`, `HIGH`, and `MIXED` snapshots for the effective corrected
  parameter version.

Monitoring uses a 30-calendar-day requested window, truncated to the current
parameter's `valid_from_date_id` so old detections are never scored against a new
threshold. Only detector flags `NORMAL` and `ANOMALY` are eligible; unusable parameter
and duration statuses are excluded from the denominator. Rows remain `WARMING_UP`
until 30 eligible results exist, then become `ELEVATED` above the larger of 10% or
twice the fitted target rate. Snapshots are idempotently stored in
`m_roll_percentile_monitor`.

## Verification strategy

- Pure fit tests cover zero filtering, recent-N selection, every status gate, and
  duration reliability.
- Persistence tests cover effective-date versioning, idempotency, and locked manual
  rows.
- CLI tests cover location/metric orchestration and `--dry_run` mapping.
- Detector tests prove that stored parameters, rather than serving history, control
  the result, and cover normal, low, high, mixed, unknown, and latest-zero direction.
- Engine tests use temporary SQLite databases for pipe and port paths.
- Schema and persistence tests cover upgrading an existing result table and storing
  directional fields.
- A read-only smoke test against the live database validates effective rows before a
  production detection run.
- Full repository tests remain scoped to `tests/` so the vendored `dify/` tree is not
  collected.
- Phase 3 verification on 2026-08-09: 39 focused tests passed; the full repository
  suite passed with 86 tests and 3 intentional skips.
- Duration/regime verification on 2026-08-15: 41 focused tests passed; the full
  repository suite passed with 90 tests and 3 intentional skips; the Next.js
  production build completed successfully.
- Canal cleanup and the first positive-only validation refit were verified on
  2026-08-15. The later zero-aware validation refit supersedes those calibration-rate
  figures; current results are recorded in `docs/TODO.md`.
- Monitoring verification on 2026-08-15: nine focused tests passed; detector and entry
  suites passed with 64 tests and one intentional skip. The first live snapshot stores
  232 direction rows covering all 58 effective location/metric parameters. It has no
  alerts yet because corrected-threshold history contains only one eligible day.
- Zero-aware validation verification on 2026-08-15: count bounds remain positive-only,
  validation and serving both retain zero counts, the locked Hormuz row remains intact,
  and the detector and entry suites pass with 67 tests and one intentional skip.
- Location-type result migration verification on 2026-08-16: all 14,020 historical
  result rows were preserved under the composite key, same-name pipe/port regression
  tests pass, the focused Python suites pass with 73 tests and one intentional skip,
  and the frontend production build completes successfully.

## Operational safeguards

- Run `main_fit_model.py --dry_run` before changing live parameter rows.
- Use a single explicit `--as_of` date when pipe and port fits must share an effective
  date.
- Record manual overrides with `fit_method='manual'` and `is_locked=1`.
- Back up the SQLite database before direct production parameter edits.
- Do not delete historical parameter versions; close their effective range.
- Treat unexpectedly long fit spans, abrupt threshold changes, and elevated live
  flag rates as review signals rather than automatically accepting a refit.

## Open decisions

- Compatibility window for the legacy quantile and `anomaly_ratio` fields.
