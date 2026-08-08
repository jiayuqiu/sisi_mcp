# Plan — duration-aware rolling-percentile detector

**Last updated:** 2026-08-08
**Status:** Fit/serve split and table-backed ship-count serving are complete. Direction,
duration serving, regime classification, and downstream presentation remain planned.

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
- Using each location's most recent 180 usable observations gives a consistent sample
  size, while recording the actual date span makes unusually long lookbacks visible.
- Duration reliability depends on the number of ships contributing to the daily
  average. Locations with a median of fewer than three ships per usable day should
  not receive duration bounds.
- In-sample threshold calibration tends to understate the threshold required during
  live scoring. A future holdout calibration phase is required.

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
- `fit_method`: currently `percentile_10_90` or `manual`.
- `fit_start_date_id` / `fit_end_date_id` / `fit_sample_size`: fitting provenance.
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
2. Remove missing and non-positive metric values. Duration also requires
   `ship_cnt > 0`.
3. Retain the most recent `recent_records` usable rows, defaulting to 180.
4. Reject fewer than 60 rows as `INSUFFICIENT` and no rows as `NO_DATA`.
5. Calculate the 10th and 90th percentiles.
6. Reject equal bounds as `FLAT`.
7. Reject ship-count upper bounds at or below three as `INSUFFICIENT`.
8. Reject duration fits whose median contributing ship count is below three.
9. Backtest rolling out-of-band ratios and derive a bounded anomaly threshold.
10. Persist a versioned row unless the current row is locked.

`fit_one_location()` remains a pure DataFrame-to-dict function so the fit rules can
be tested independently of database persistence.

## Serve contract

For the requested serving date, location, and metric:

1. Load the single parameter row effective on that date.
2. Return `NO_DATA` when no effective row exists.
3. Map non-OK fit statuses to their detector flags without scoring observations.
4. Use the stored bounds, interval, and anomaly threshold.
5. Score only the most recent configured interval.
6. Preserve the existing latest-zero sentinel behaviour until direction and duration
   output replaces it deliberately.

The current serving phase scores `ship_cnt` only. The legacy quantile output columns
are retained for compatibility even though the stored lower and upper bounds are now
authoritative.

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

- [ ] Count observations below the lower bound separately from observations above the
  upper bound.
- [ ] Persist `ratio_low` and `ratio_high`.
- [ ] Define and emit direction values with explicit tie behaviour.
- [ ] Migrate API and prompt consumers away from the ambiguous single ratio.

### Phase 4 — duration serving

- [ ] Load the effective duration parameter row alongside the ship-count row.
- [ ] Score duration with its stored interval, bounds, threshold, and status.
- [ ] Define missing-duration behaviour independently from missing ship-count data.
- [ ] Persist duration ratios, direction, and status.

### Phase 5 — regime and presentation

- [ ] Define the count/duration regime matrix and names. `AVOIDANCE`, `BLOCKAGE`, and
  congestion-related outcomes are candidates; final labels require validation.
- [ ] Widen the anomaly result schema without breaking existing reads.
- [ ] Update Dify prompts and API responses.
- [ ] Update plots and frontend presentation.
- [ ] Backfill or explicitly version historical result semantics.

### Phase 6 — calibration and data quality

- [ ] Add holdout or rolling-origin threshold calibration.
- [ ] Apply reviewed location-specific `fit_start` floors where regime breaks are
  known.
- [ ] Resolve Panama and Suez records incorrectly routed as ports.
- [ ] Monitor live flag rates by location, metric, and direction.

## Verification strategy

- Pure fit tests cover zero filtering, recent-N selection, every status gate, and
  duration reliability.
- Persistence tests cover effective-date versioning, idempotency, and locked manual
  rows.
- CLI tests cover location/metric orchestration and `--dry_run` mapping.
- Detector tests prove that stored parameters, rather than serving history, control
  the result.
- Engine tests use temporary SQLite databases for pipe and port paths.
- A read-only smoke test against the live database validates effective rows before a
  production detection run.
- Full repository tests remain scoped to `tests/` so the vendored `dify/` tree is not
  collected.

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

- Exact direction enum and tie-breaking when high and low ratios are equal.
- Whether latest-zero remains a sentinel or becomes an ordinary low-direction score.
- Final count/duration regime names and thresholds.
- Compatibility window for the legacy quantile and `anomaly_ratio` fields.
- Holdout method: fixed split, rolling origin, or time-blocked cross-validation.
