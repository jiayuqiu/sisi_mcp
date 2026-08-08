# TODO — duration-aware detector rework

**Last updated:** 2026-08-08
**Plan:** `docs/plan-duration-aware-detector.md`

The fit side of the rolling-percentile fit/serve split and ship-count serving from
the stored parameter table are complete and committed. Duration-aware detection and
the downstream reporting changes remain to be implemented.

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
- [x] Fit each location using its own most recent 180 usable records and record the
  actual `fit_start_date_id` / `fit_end_date_id` span.
- [x] Assign `OK`, `FLAT`, `INSUFFICIENT`, or `NO_DATA` at fit time and leave bounds
  NULL for non-OK fits.
- [x] Support versioned, idempotent parameter persistence.
- [x] Respect `is_locked` rows during refitting.
- [x] Populate the live parameter table with 62 rows: 52 `OK`, 8 `INSUFFICIENT`, and
  2 `NO_DATA`.
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

## Detection and reporting work

- [ ] Split `anomaly_ratio` into `ratio_high` and `ratio_low`.
- [ ] Emit anomaly direction so a traffic surge and a traffic collapse do not produce
  byte-identical result rows.
- [ ] Add the fitted duration channel to `detect()`; duration parameter rows already
  exist.
- [ ] Define the combined count/duration regime matrix, including outcomes such as
  `AVOIDANCE` and `BLOCKAGE`.
- [ ] Widen `m_pipe_anomaly_roll_percentile` to store direction and duration results.
- [ ] Update the Dify/API prompt templates and consumers for the new result fields.
- [ ] Update plots to display direction and duration anomalies.
- [ ] Update the frontend for the widened detector output.

---

## Open data and calibration issues

### Sparse locations cross possible regime breaks

- [ ] Define and apply location-specific `fit_start` floors. The argument exists, but
  no production fitting configuration currently uses it.

The worst observed fitting spans start at 南沙港 `20231108`, 阿布扎比港 `20240507`,
杰贝阿里 `20240618`, and 德班港 `20240713`. Recent-N controls sample size but can
still reach back across a regime change.

### Canals duplicated as ports

- [ ] Investigate BCI routing/source data for 巴拿马运河 and 苏伊士运河.
- [ ] Remove or prevent invalid `port/巴拿马运河` and `port/苏伊士运河` parameter rows
  once the source-routing rule is confirmed.

Both have 1,529 port rows, zero duration values, and counts stopping at `20260422`,
while real port data continues to `20260725`.

### Thresholds calibrated in-sample

- [ ] Add a holdout or out-of-sample split to `_derive_threshold()`.
- [ ] Revalidate per-location thresholds and the target live flag rate after the
  holdout change.

The current implementation derives bounds and backtests thresholds on the same
records. `target_flag_rate` is a stopgap; previous out-of-sample checking needed
thresholds around 0.20–0.60, compared with 0.20–0.40 in-sample.

---

## Verification status

- [x] Detector and fit-CLI tests pass: 33 passed, 0 skipped.
- [x] Live-data fitting smoke test passes in `--dry_run` mode.
- [ ] Obtain a clean full `uv run pytest tests/` result.

The 2026-08-08 full-suite check was stopped at the first failure:
`TestDeepSeekClient.test_search_and_ask` could not resolve `api.deepseek.com` in the
restricted environment. This differs from the older four `TestDetectAnomaly`
failures previously recorded here, so the complete current failure set is not yet
known. Always scope pytest to `tests/`; bare pytest also collects the vendored
`dify/` tree.
