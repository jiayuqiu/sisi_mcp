# TODO — duration-aware detector rework

**Last updated:** 2026-07-27
**Plan:** `docs/plan-duration-aware-detector.md` (background, evidence, phases)

Working through a fit/serve split for the rolling-percentile detector, so bounds come
from a stored parameter table instead of being recomputed from a trailing window on
every run. Steps 1 and 2 are done; the detector itself has not been touched yet.

---

## Done

### 1. `m_roll_percentile_parameter` table

`mcp_conductor/entry/main_setup_schema.py` — added
`SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER` and its `conn.execute` call. Run against the
live DB; all other tables intact.

Key is `(location_type, location_name, metric, valid_from_date_id)`.
`location_type` + `location_name` deliberately replace the `pipe_name` column that
`m_pipe_anomaly_roll_percentile` uses for both pipes and ports.

`CLAUDE.md` schema section updated.

### 2. The fit job

- `mcp_conductor/detector/roll_percentile/fit.py` — library. `fit_one_location()` is a
  pure DataFrame→dict function (no DB) holding the gating rules;
  `fit_roll_percentile_parameters()` loops a location type and persists.
- `mcp_conductor/entry/main_fit_model.py` — `fit_model()` plus the CLI.

```bash
uv run python mcp_conductor/entry/main_fit_model.py --dry_run
uv run python mcp_conductor/entry/main_fit_model.py
```

Behaviour, all verified against real data:

- **Zeros excluded.** `metric > 0`, and for duration also `ship_cnt > 0`. Without this
  the 10th percentile is 0.0 on every location.
- **Per-location recent-N.** Each location fits on its own most recent 180 non-zero
  records (`DEFAULT_RECENT_RECORDS`), not a shared calendar window. The span actually
  covered is written to `fit_start_date_id` / `fit_end_date_id`.
- **Status set at fit time.** `OK` / `FLAT` / `INSUFFICIENT` / `NO_DATA`. These are
  statements about history, so they belong here rather than in `detect()`. Bounds are
  written NULL on any non-OK status.
- **`is_locked` respected.** Verified: a row locked as manual `[15,25]` survived a
  refit on a later window untouched, while unlocked rows versioned correctly (old row
  closed at `valid_from - 1`, new row in force). Re-running an identical fit is
  idempotent — held at 17 rows.

### 3. Table populated

62 rows: **52 `OK`, 8 `INSUFFICIENT`, 2 `NO_DATA`**.
`valid_from` is `20260722` for pipes and `20260726` for ports (`as_of_date_id` defaults
per table to that table's max `date_id`; pipe data ends `20260721`, port data
`20260725`). Pass `--as_of` for a single effective date across the batch.

Backup of the pre-fit DB:
`/tmp/claude-1000/-home-jerry-codebase-sisimcp/4515c273-98f9-44a9-a32d-ac7d86b5d6af/scratchpad/sisi.pre-fit.bak`
(scratchpad — copy it somewhere durable if it still matters.)

### 4. BCI sync validation (side fix)

`main_sync_bci_data.py` — the strict field validation was aborting the whole day's
sync on one malformed item. Moved the `try` inside the loop: malformed items log at
ERROR and increment `malformed_count`, valid rows still commit. A day where
*everything* was malformed still fails, with `reason: "malformed_items"`.

---

## Next up

### Immediate

1. **Lock 霍尔木兹海峡 and delete the hardcode.** `rolling_percentile.py:110-112` still
   contains `if name_str == "霍尔木兹海峡": quantile_25 = 15; quantile_75 = 25`. The
   fitted row for it is `[1, 18]` off a span starting `20250829` — very wide, because
   that span includes the near-zero months of 2025-10/11 (monthly mean count 4.90 then
   0.30). Set `is_locked = 1` with the intended bounds, then remove the branch.
2. **Point `detect()` at the table.** Replace the inline `np.percentile` calls with a
   lookup of the row in force for `run_date`; short-circuit when `status != 'OK'`.
   This is the step that makes any of the above matter — nothing reads the table yet.
3. Move `mcp_conductor/detector/generic/rolling_percentile.py` to `mcp_conductor/detector/roll_percentile`
4. Update `roll_percentile` detect logics. Currently is based on dynamic parameter (p25, p75). After table `m_roll_percentile_parameter` created, need to load parameters from table and feed into roll percentile model.

### Then (from the plan doc)

3. Split `anomaly_ratio` into `ratio_high` / `ratio_low` and emit a direction. Today a
   surge and a collapse produce byte-identical rows — verified on 对马海峡: `20230416`
   (18 of 30 days above p75) and `20240224` (15 of 30 below p25) both save
   `anomaly_flag=1, anomaly_ratio=0.60`.
4. Add the duration channel to `detect()` — the parameter rows already exist.
5. Regime matrix (`AVOIDANCE` vs `BLOCKAGE` etc.), schema widening for
   `m_pipe_anomaly_roll_percentile`, prompt templates, plot, frontend.

---

## Open issues

### Sparse locations reach back years for their 180 records

南沙港 needed data from `20231108` — a 2.7-year span — while busy locations reach back
only ~6 months. Recent-N adapts the sample size but cannot tell that it crossed a
regime break. The `fit_start` argument exists for this and **nothing is using it yet**.

Worst offenders by span start: 南沙港 `20231108`, 阿布扎比港 `20240507`,
杰贝阿里 `20240618`, 德班港 `20240713`.

### The canals are duplicated as ports

`ship_cnt_in_port` holds 1,529 rows each for 巴拿马运河 and 苏伊士运河, with **zero**
duration values, and counts stopping at `20260422` — three months stale while real
ports run to `20260725`. Looks like a BCI routing or source-data problem rather than a
fitting one. They currently produce `port/巴拿马运河` and `port/苏伊士运河` parameter
rows that probably should not exist.

### Thresholds are calibrated in-sample

`_derive_threshold()` backtests on the same records used to fit the bounds, so live
flag rates will run above `target_flag_rate` (default 0.05). Out-of-sample checking
(fit 2024, score 2025) wanted 0.20–0.60 where in-sample gives 0.20–0.40. A holdout
split inside `_derive_threshold` would fix it; `target_flag_rate` is the stopgap.

### Pre-existing test failures — not ours

`uv run pytest tests/` → **4 failed, 75 passed, 3 skipped**. All four are
`TestDetectAnomaly`, failing inside `parse_question_json` at
`dify_api_server.py:113`. Confirmed identical with this work stashed. Related to
`docs/plan-detect-anomaly-question-parsing.md`.

Note: bare `uv run pytest` tries to collect the vendored `dify/` tree and dies with
282 collection errors. Always scope to `tests/`.

---

## Uncommitted at time of writing

```
 M CLAUDE.md
 M mcp_conductor/detector/detect_engine.py     <- yours: SELECT * -> explicit columns
 M mcp_conductor/entry/main_setup_schema.py
 M mcp_conductor/entry/main_sync_bci_data.py
 M tests/mcp_conductor/entry/test_main_sync_bci_data.py
 M tests/mcp_conductor/resources/sisi/APIs/test_metrics_api.py
 M tests/mcp_conductor/resources/sisi/APIs/test_sisi_client.py
?? docs/plan-duration-aware-detector.md
?? docs/TODO.md
?? mcp_conductor/detector/roll_percentile/
?? mcp_conductor/entry/main_fit_model.py
```

Nothing committed this session, and `mcp_conductor/detector/roll_percentile/` has no
tests yet — `fit_one_location()` is pure and is the natural place to start.
