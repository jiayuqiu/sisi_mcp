"""
Fit the frozen detection bounds used by RollingPercentileDetector and persist them
to m_roll_percentile_parameter.

This is the "fit" half of a fit/serve split: bounds are derived once here from each
location's recent history, and the detector reads them back instead of recomputing
quantiles on every run. That removes the leak in the old design (the 30-day window
being scored was itself part of the 365 days defining "normal") and makes a re-run of
an old date reproducible.

Run it via mcp_conductor/entry/main_fit_model.py.

See docs/plan-duration-aware-detector.md for the analysis behind the constants below.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from mcp_conductor.detector.detect_engine import get_pipe_name_list, get_port_name_list
from mcp_conductor.resources.utils.db import get_engine
from mcp_conductor.resources.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path("./data/sisi.sqlite")

PARAM_TABLE = "m_roll_percentile_parameter"

# Trusted map — table and column names are interpolated into SQL from here, never
# from caller input.
LOCATION_SPECS: dict[str, dict] = {
    "pipe": {"table": "ship_cnt_in_pipe", "key_col": "pipe_name", "name_list": get_pipe_name_list},
    "port": {"table": "ship_cnt_in_port", "key_col": "port_name", "name_list": get_port_name_list},
}

VALID_METRICS = ("ship_cnt", "duration")

STATUS_OK = "OK"
STATUS_FLAT = "FLAT"
STATUS_INSUFFICIENT = "INSUFFICIENT"
STATUS_NO_DATA = "NO_DATA"

FIT_METHOD_PERCENTILE = "percentile_10_90_holdout"

LOWER_PERCENTILE = 10
UPPER_PERCENTILE = 90

# Minimum usable (non-zero) training observations before bounds are trustworthy.
MIN_FIT_SAMPLE = 60

# ship_cnt: a p90 this low means the counts are too small to separate signal from noise.
# Carried over from the inline gate in RollingPercentileDetector.detect().
MIN_COUNT_UPPER_BOUND = 3

# duration: it is a per-ship mean, so its reliability scales with how many ships were
# averaged. Locations whose typical day carries fewer than this many ships get no
# duration bounds — a 1-ship daily mean is noise, not a transit time.
MIN_DURATION_SAMPLE_SHIPS = 3

DEFAULT_INTERVAL_DAYS = 30

# Each fit retains a fixed-size validation block plus the most recent positive
# training records that fit within the remaining budget. This lets quiet locations
# reach back further for normal examples without dropping zero-count validation days.
DEFAULT_RECENT_RECORDS = 180

# The latest observations are held out chronologically. Bounds are fitted only on
# the earlier records, then frozen while rolling ratios are evaluated on the holdout.
DEFAULT_HOLDOUT_RECORDS = 30
MIN_HOLDOUT_RECORDS = 30

# Sparse ports with a long break in source coverage must not fill a recent-N sample
# from the older, pre-break regime.  These four locations have fragmented coverage
# after July 2024 and resume sustained current-era coverage in January 2026.  The
# floor is location-specific so complete locations retain their full recent history.
#
# A floor only applies when fitting on or after it.  That keeps historical as-of fits
# reproducible: fitting a 2025 date still uses the data that existed in 2025.
LOCATION_FIT_START_FLOORS: dict[tuple[str, str], int] = {
    ("port", "南沙港"): 20260101,
    ("port", "阿布扎比港"): 20260101,
    ("port", "杰贝阿里"): 20260101,
    ("port", "德班港"): 20260101,
}

# Threshold derivation: pick the ratio quantile that leaves this share of days flagged
# over the fit window. A global 0.5 cannot serve every location — measured per-strait
# thresholds for a ~5% flag rate span 0.20 to 0.60.
DEFAULT_TARGET_FLAG_RATE = 0.05
THRESHOLD_FLOOR = 0.20
THRESHOLD_CEILING = 0.80


def _load_history(
    table: str,
    key_col: str,
    location_name: str,
    as_of_date_id: int,
    engine,
    fit_start: int | None = None,
) -> pd.DataFrame:
    """
    Load date_id, ship_cnt and duration for one location, up to and including
    `as_of_date_id`. `fit_start` is an optional hard floor, used to keep a fit from
    reaching back across a known regime break.
    """
    params: dict = {"name": location_name, "as_of": as_of_date_id}
    floor_clause = ""
    if fit_start is not None:
        floor_clause = "AND date_id >= :fit_start"
        params["fit_start"] = fit_start

    sql = text(
        f"""
        SELECT date_id, ship_cnt, duration
        FROM {table}
        WHERE {key_col} = :name
          AND date_id <= :as_of
          {floor_clause}
        ORDER BY date_id
        """
    )
    return pd.read_sql(sql, con=engine, params=params)


def _max_date_id(table: str, engine) -> int | None:
    """Latest date_id present in a source table, used as the default as-of date."""
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT MAX(date_id) FROM {table}")).scalar()


def resolve_fit_start(
    location_type: str,
    location_name: str,
    as_of_date_id: int,
    requested_fit_start: int | None = None,
) -> int | None:
    """Return the effective history floor for one location.

    Production location floors protect sparse series from reaching across a known
    data/regime break.  A caller may request a later floor, but cannot accidentally
    weaken the configured protection by requesting an earlier one.  Configured
    floors later than ``as_of_date_id`` do not apply to historical fits.
    """
    candidates = [requested_fit_start] if requested_fit_start is not None else []
    configured_floor = LOCATION_FIT_START_FLOORS.get((location_type, location_name))
    if configured_floor is not None and configured_floor <= as_of_date_id:
        candidates.append(configured_floor)
    return max(candidates) if candidates else None


def _usable_rows(history: pd.DataFrame, metric: str) -> pd.DataFrame:
    """
    Restrict history to the rows that carry signal for `metric`.

    Zeros are dropped rather than kept as low values: P(duration = 0 | ship_cnt = 0) is
    0.96-1.00 across every strait, so a zero records "no ships were measured", not
    "the transit was instant". Leaving them in pins the 10th percentile at 0.0 for
    every location and the lower bound stops meaning anything.

    For duration the mask is on ship_cnt as well, since a per-ship mean is undefined
    on a day with no ships.
    """
    rows = _scoring_rows(history, metric)
    return rows[rows[metric] > 0]


def _scoring_rows(history: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Return observations that serving can score for ``metric``.

    Ship-count zeros are retained because zero traffic is a real low-side signal.
    Missing counts are not observations. Duration keeps its existing serving rule:
    only positive durations backed by at least one contributing ship are scoreable.
    """
    rows = history.dropna(subset=[metric])
    if metric == "duration":
        rows = rows[rows["ship_cnt"].fillna(0) > 0]
        rows = rows[rows[metric] > 0]
    return rows.sort_values("date_id")


def _derive_threshold(
    training: pd.DataFrame,
    holdout: pd.DataFrame,
    metric: str,
    lower_bound: float,
    upper_bound: float,
    interval_days: int,
    target_flag_rate: float,
) -> tuple[float, float | None]:
    """
    Evaluate a band fitted on ``training`` against later ``holdout`` observations.

    ``training`` here is the pre-validation scoring series, not the positive-only
    sample used to fit bounds. The last ``interval_days - 1`` observations seed the
    first holdout scoring window, matching rolling-origin serving without allowing
    any holdout observation to influence the fitted bounds. Returns the threshold
    and the realized share of holdout windows flagged by serving semantics.

    Scoring mirrors serving: a rolling window over usable observations, with anomaly
    status triggered only when the ratio is strictly greater than the threshold.
    """
    seed = training.sort_values("date_id").tail(max(interval_days - 1, 0))
    scoring_rows = pd.concat([seed, holdout.sort_values("date_id")], ignore_index=True)
    values = scoring_rows[metric].to_numpy()
    out_of_band = (values < lower_bound) | (values > upper_bound)
    ratios = pd.Series(out_of_band).rolling(interval_days).mean().dropna().to_numpy()
    if len(ratios) < len(holdout):
        logger.debug("Not enough context to calibrate a threshold; using floor %.2f", THRESHOLD_FLOOR)
        return THRESHOLD_FLOOR, None

    holdout_ratios = ratios[-len(holdout):]

    threshold = float(np.percentile(holdout_ratios, 100.0 * (1.0 - target_flag_rate)))
    threshold = float(min(max(threshold, THRESHOLD_FLOOR), THRESHOLD_CEILING))
    flagged = holdout_ratios > threshold
    if metric == "ship_cnt":
        # Serving preserves the compatibility rule that a latest zero is always
        # anomalous, even when its rolling low ratio has not crossed the threshold.
        flagged = flagged | (holdout[metric].to_numpy() == 0)
    realized_flag_rate = float(np.mean(flagged))
    return threshold, realized_flag_rate


def fit_one_location(
    history: pd.DataFrame,
    metric: str,
    recent_records: int = DEFAULT_RECENT_RECORDS,
    interval_days: int = DEFAULT_INTERVAL_DAYS,
    target_flag_rate: float = DEFAULT_TARGET_FLAG_RATE,
    holdout_records: int = DEFAULT_HOLDOUT_RECORDS,
) -> dict:
    """
    Derive bounds and threshold from chronological training and validation blocks.

    Normal bounds use positive observations only. The validation block mirrors live
    scoring: ship-count zeros are retained as low-side signals, while duration keeps
    only usable positive observations. ``recent_records`` is the total retained
    training-plus-validation budget.

    Pure function over a DataFrame — no DB access — so the gating rules can be tested
    directly.

    Returns:
        Fit result and calibration provenance. Bounds are based only on the training
        block. ``fit_sample_size`` covers training plus holdout observations.
    """
    if holdout_records < MIN_HOLDOUT_RECORDS:
        raise ValueError(
            f"holdout_records must be >= {MIN_HOLDOUT_RECORDS}, got {holdout_records}"
        )

    scoring = _scoring_rows(history, metric)
    holdout = scoring.tail(holdout_records)
    pre_holdout_scoring = scoring.iloc[:-len(holdout)] if len(holdout) else scoring

    # Split chronologically before removing zeros. This prevents validation zeros
    # from being skipped and replaced with older positive observations.
    training = _usable_rows(pre_holdout_scoring, metric)
    if recent_records:
        training = training.tail(max(recent_records - holdout_records, 0))

    retained = pd.concat([training, holdout], ignore_index=True).sort_values("date_id")
    sample_size = len(retained)
    fit_start_date_id = int(retained["date_id"].iloc[0]) if sample_size else None
    fit_end_date_id = int(retained["date_id"].iloc[-1]) if sample_size else None

    training_sample_size = 0
    calibration_start_date_id = None
    calibration_end_date_id = None
    calibration_sample_size = 0
    calibration_flag_rate = None

    def _rejected(status: str) -> dict:
        return {
            "lower_bound": None,
            "upper_bound": None,
            "anomaly_threshold": THRESHOLD_FLOOR,  # unused: status != OK short-circuits
            "status": status,
            "fit_sample_size": sample_size,
            "fit_start_date_id": fit_start_date_id,
            "fit_end_date_id": fit_end_date_id,
            "training_sample_size": training_sample_size,
            "calibration_start_date_id": calibration_start_date_id,
            "calibration_end_date_id": calibration_end_date_id,
            "calibration_sample_size": calibration_sample_size,
            "calibration_target_flag_rate": target_flag_rate,
            "calibration_flag_rate": calibration_flag_rate,
        }

    if _usable_rows(history, metric).empty:
        return _rejected(STATUS_NO_DATA)
    if len(holdout) < holdout_records or len(training) < MIN_FIT_SAMPLE:
        return _rejected(STATUS_INSUFFICIENT)

    training_sample_size = len(training)
    calibration_sample_size = len(holdout)
    calibration_start_date_id = int(holdout["date_id"].iloc[0])
    calibration_end_date_id = int(holdout["date_id"].iloc[-1])

    values = training[metric]
    lower_bound = float(np.percentile(values, LOWER_PERCENTILE))
    upper_bound = float(np.percentile(values, UPPER_PERCENTILE))

    if lower_bound == upper_bound:
        return _rejected(STATUS_FLAT)

    if metric == "ship_cnt" and upper_bound <= MIN_COUNT_UPPER_BOUND:
        return _rejected(STATUS_INSUFFICIENT)

    if metric == "duration" and retained["ship_cnt"].median() < MIN_DURATION_SAMPLE_SHIPS:
        # Too few ships per day for a daily mean transit time to mean anything.
        return _rejected(STATUS_INSUFFICIENT)

    threshold, calibration_flag_rate = _derive_threshold(
        training=pre_holdout_scoring,
        holdout=holdout,
        metric=metric,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        interval_days=interval_days,
        target_flag_rate=target_flag_rate,
    )

    return {
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "anomaly_threshold": threshold,
        "status": STATUS_OK,
        "fit_sample_size": sample_size,
        "fit_start_date_id": fit_start_date_id,
        "fit_end_date_id": fit_end_date_id,
        "training_sample_size": training_sample_size,
        "calibration_start_date_id": calibration_start_date_id,
        "calibration_end_date_id": calibration_end_date_id,
        "calibration_sample_size": calibration_sample_size,
        "calibration_target_flag_rate": target_flag_rate,
        "calibration_flag_rate": calibration_flag_rate,
    }


def _next_date_id(date_id: int) -> int:
    """YYYYMMDD -> the following day, as YYYYMMDD."""
    return int((datetime.strptime(str(date_id), "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d"))


def _previous_date_id(date_id: int) -> int:
    """YYYYMMDD -> the preceding day, as YYYYMMDD."""
    return int((datetime.strptime(str(date_id), "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d"))


def _is_locked(
    conn: sqlite3.Connection,
    location_type: str,
    location_name: str,
    metric: str,
    valid_from: int,
) -> bool:
    """True when a manual row is in force on the proposed effective date.

    The date predicate matters for chronological rebuilds: a future manual override
    must not prevent fitting an earlier automated version.
    """
    row = conn.execute(
        f"""
        SELECT 1 FROM {PARAM_TABLE}
        WHERE location_type = ? AND location_name = ? AND metric = ?
          AND valid_from_date_id <= ?
          AND (valid_to_date_id IS NULL OR valid_to_date_id >= ?)
          AND is_locked = 1
        ORDER BY valid_from_date_id DESC
        LIMIT 1
        """,
        (location_type, location_name, metric, valid_from, valid_from),
    ).fetchone()
    return row is not None


def _persist(
    conn: sqlite3.Connection,
    location_type: str,
    location_name: str,
    metric: str,
    valid_from: int,
    interval_days: int,
    fitted: dict,
) -> None:
    """Insert one version and maintain its neighboring effective-date boundaries.

    Looking up both neighbors makes persistence safe when a historical rebuild writes
    versions out of order. A later version may already exist in the database.
    """
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    next_row = conn.execute(
        f"""
        SELECT MIN(valid_from_date_id)
        FROM {PARAM_TABLE}
        WHERE location_type = ? AND location_name = ? AND metric = ?
          AND valid_from_date_id > ?
        """,
        (location_type, location_name, metric, valid_from),
    ).fetchone()
    next_valid_from = next_row[0] if next_row else None
    valid_to = _previous_date_id(next_valid_from) if next_valid_from is not None else None

    # Shorten the immediately preceding automated row. Locked manual history is never
    # rewritten here; an effective locked row is filtered by _is_locked before this.
    conn.execute(
        f"""
        UPDATE {PARAM_TABLE}
        SET valid_to_date_id = ?, updated_timestamp_utc = ?
        WHERE location_type = ? AND location_name = ? AND metric = ?
          AND is_locked = 0
          AND valid_from_date_id = (
              SELECT MAX(valid_from_date_id)
              FROM {PARAM_TABLE}
              WHERE location_type = ? AND location_name = ? AND metric = ?
                AND valid_from_date_id < ?
          )
        """,
        (
            _previous_date_id(valid_from), updated_at,
            location_type, location_name, metric,
            location_type, location_name, metric, valid_from,
        ),
    )

    # ON CONFLICT rather than a plain INSERT so re-running the same fit is idempotent.
    conn.execute(
        f"""
        INSERT INTO {PARAM_TABLE} (
            location_type, location_name, metric, valid_from_date_id, valid_to_date_id,
            lower_bound, upper_bound, anomaly_threshold, interval_days, status,
            fit_method, fit_start_date_id, fit_end_date_id, fit_sample_size,
            training_sample_size, calibration_start_date_id, calibration_end_date_id,
            calibration_sample_size, calibration_target_flag_rate, calibration_flag_rate,
            is_locked, updated_timestamp_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(location_type, location_name, metric, valid_from_date_id) DO UPDATE SET
            valid_to_date_id      = excluded.valid_to_date_id,
            lower_bound           = excluded.lower_bound,
            upper_bound           = excluded.upper_bound,
            anomaly_threshold     = excluded.anomaly_threshold,
            interval_days         = excluded.interval_days,
            status                = excluded.status,
            fit_method            = excluded.fit_method,
            fit_start_date_id     = excluded.fit_start_date_id,
            fit_end_date_id       = excluded.fit_end_date_id,
            fit_sample_size       = excluded.fit_sample_size,
            training_sample_size  = excluded.training_sample_size,
            calibration_start_date_id = excluded.calibration_start_date_id,
            calibration_end_date_id = excluded.calibration_end_date_id,
            calibration_sample_size = excluded.calibration_sample_size,
            calibration_target_flag_rate = excluded.calibration_target_flag_rate,
            calibration_flag_rate = excluded.calibration_flag_rate,
            updated_timestamp_utc = excluded.updated_timestamp_utc
        """,
        (
            location_type, location_name, metric, valid_from, valid_to,
            fitted["lower_bound"], fitted["upper_bound"], fitted["anomaly_threshold"],
            interval_days, fitted["status"],
            FIT_METHOD_PERCENTILE,
            fitted["fit_start_date_id"], fitted["fit_end_date_id"], fitted["fit_sample_size"],
            fitted["training_sample_size"], fitted["calibration_start_date_id"],
            fitted["calibration_end_date_id"], fitted["calibration_sample_size"],
            fitted["calibration_target_flag_rate"], fitted["calibration_flag_rate"],
            updated_at,
        ),
    )


def fit_roll_percentile_parameters(
    location_type: str,
    metric: str,
    recent_records: int = DEFAULT_RECENT_RECORDS,
    as_of_date_id: int | None = None,
    fit_start: int | None = None,
    interval_days: int = DEFAULT_INTERVAL_DAYS,
    target_flag_rate: float = DEFAULT_TARGET_FLAG_RATE,
    holdout_records: int = DEFAULT_HOLDOUT_RECORDS,
    persist: bool = True,
    engine=None,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """
    Fit detection parameters for every location of one type and write them to
    m_roll_percentile_parameter.

    Each location reserves its latest scoring observations for validation, including
    zero ship counts, then fills the remaining ``recent_records`` budget with the
    latest positive training observations. The calendar span therefore varies by
    location, and is recorded in fit_start_date_id / fit_end_date_id.

    Args:
        location_type   : 'pipe' or 'port'.
        metric          : 'ship_cnt' or 'duration'.
        recent_records  : total training-plus-validation record budget. Training uses
                          positive observations; ship-count validation retains zeros.
                          Pass 0 to use all available training observations.
        as_of_date_id   : YYYYMMDD; ignore data after this date. Defaults to the latest
                          date present in the source table. The fitted rows take effect
                          the day after.
        fit_start       : optional global YYYYMMDD floor. Location-specific production
                          floors are also applied; the later applicable floor wins.
        interval_days   : detection window the threshold is calibrated for.
        target_flag_rate: share of windows the threshold should leave flagged over the
                          chronological holdout.
        holdout_records  : latest scoring observations reserved for calibration.
                          Ship-count zeros are included; unusable durations are not.
        persist         : set False to compute without writing (useful for comparing
                          candidate fit settings).
        engine          : SQLAlchemy engine for reads; defaults to the shared one.
        conn            : sqlite3 connection for writes; opened and closed here if omitted.

    Returns:
        One dict per location, including those skipped as locked (marked with
        "skipped": "locked").

    Warning:
        Recent-N adapts the span but does not detect regime breaks. 苏伊士运河 fits to
        [8, 22] on 2023 data and [1, 4] on 2024; if its recent 180 records straddle
        that break the bounds will span both regimes and match neither. Use fit_start
        to exclude a known disruption.

    Raises:
        ValueError: on an unknown location_type or metric, or a negative recent_records.
    """
    if location_type not in LOCATION_SPECS:
        raise ValueError(f"location_type must be one of {sorted(LOCATION_SPECS)}, got {location_type!r}")
    if metric not in VALID_METRICS:
        raise ValueError(f"metric must be one of {list(VALID_METRICS)}, got {metric!r}")
    if recent_records < 0:
        raise ValueError(f"recent_records must be >= 0, got {recent_records}")
    if holdout_records < MIN_HOLDOUT_RECORDS:
        raise ValueError(
            f"holdout_records must be >= {MIN_HOLDOUT_RECORDS}, got {holdout_records}"
        )

    spec = LOCATION_SPECS[location_type]
    engine = engine or get_engine()

    if as_of_date_id is None:
        as_of_date_id = _max_date_id(spec["table"], engine)
        if as_of_date_id is None:
            raise ValueError(f"{spec['table']} is empty; nothing to fit.")
        logger.info("as_of_date_id defaulted to %s (latest in %s).", as_of_date_id, spec["table"])
    valid_from = _next_date_id(as_of_date_id)

    owns_conn = persist and conn is None
    if persist and conn is None:
        conn = sqlite3.connect(str(DB_PATH.absolute()))

    results: list[dict] = []
    try:
        for location_name in spec["name_list"](engine):
            if persist and _is_locked(conn, location_type, location_name, metric, valid_from):
                logger.info(
                    "%s/%s/%s: manual override in force, skipping refit.",
                    location_type, location_name, metric,
                )
                results.append({
                    "location_type": location_type,
                    "location_name": location_name,
                    "metric": metric,
                    "skipped": "locked",
                })
                continue

            location_fit_start = resolve_fit_start(
                location_type=location_type,
                location_name=location_name,
                as_of_date_id=as_of_date_id,
                requested_fit_start=fit_start,
            )
            history = _load_history(
                spec["table"],
                spec["key_col"],
                location_name,
                as_of_date_id,
                engine,
                location_fit_start,
            )
            fitted = fit_one_location(
                history=history,
                metric=metric,
                recent_records=recent_records,
                interval_days=interval_days,
                target_flag_rate=target_flag_rate,
                holdout_records=holdout_records,
            )

            if persist:
                _persist(
                    conn=conn,
                    location_type=location_type,
                    location_name=location_name,
                    metric=metric,
                    valid_from=valid_from,
                    interval_days=interval_days,
                    fitted=fitted,
                )

            results.append({
                "location_type": location_type,
                "location_name": location_name,
                "metric": metric,
                "valid_from_date_id": valid_from,
                "interval_days": interval_days,
                "holdout_records": holdout_records,
                "fit_floor_date_id": location_fit_start,
                **fitted,
            })
            logger.info(
                "%s/%s/%s: status=%s bounds=[%s, %s] threshold=%s n=%d train=%d holdout=%d holdout_flags=%s floor=%s span=%s-%s",
                location_type, location_name, metric, fitted["status"],
                fitted["lower_bound"], fitted["upper_bound"],
                fitted["anomaly_threshold"], fitted["fit_sample_size"],
                fitted["training_sample_size"], fitted["calibration_sample_size"],
                fitted["calibration_flag_rate"],
                location_fit_start,
                fitted["fit_start_date_id"], fitted["fit_end_date_id"],
            )

        if persist:
            conn.commit()
    finally:
        if owns_conn:
            conn.close()

    logger.info(
        "Fitted %s/%s: %d locations, %d OK, %d skipped as locked.",
        location_type, metric, len(results),
        sum(1 for r in results if r.get("status") == STATUS_OK),
        sum(1 for r in results if r.get("skipped") == "locked"),
    )
    return results
