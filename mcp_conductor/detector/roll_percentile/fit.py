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

FIT_METHOD_PERCENTILE = "percentile_10_90"

LOWER_PERCENTILE = 10
UPPER_PERCENTILE = 90

# Minimum usable (non-zero) days before a fit is trustworthy at all.
MIN_FIT_SAMPLE = 60

# ship_cnt: a p90 this low means the counts are too small to separate signal from noise.
# Carried over from the inline gate in RollingPercentileDetector.detect().
MIN_COUNT_UPPER_BOUND = 3

# duration: it is a per-ship mean, so its reliability scales with how many ships were
# averaged. Locations whose typical day carries fewer than this many ships get no
# duration bounds — a 1-ship daily mean is noise, not a transit time.
MIN_DURATION_SAMPLE_SHIPS = 3

DEFAULT_INTERVAL_DAYS = 30

# Locations are fitted on their own most recent N usable records rather than a shared
# calendar window, so a quiet location reaches back further in time for the same
# sample size instead of being rejected for sparseness.
DEFAULT_RECENT_RECORDS = 180

# Threshold derivation: pick the ratio quantile that leaves this share of days flagged
# over the fit window. A global 0.5 cannot serve every location — measured per-strait
# thresholds for a ~5% flag rate span 0.20 to 0.60.
DEFAULT_TARGET_FLAG_RATE = 0.05
THRESHOLD_FLOOR = 0.20
THRESHOLD_CEILING = 0.80
MIN_BACKTEST_WINDOWS = 30


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
    rows = history.dropna(subset=[metric])
    if metric == "duration":
        rows = rows[rows["ship_cnt"].fillna(0) > 0]
    return rows[rows[metric] > 0]


def _derive_threshold(
    usable: pd.DataFrame,
    metric: str,
    lower_bound: float,
    upper_bound: float,
    interval_days: int,
    target_flag_rate: float,
) -> float:
    """
    Backtest the frozen band across the fit window and return the anomaly_threshold
    that leaves `target_flag_rate` of windows flagged.

    Scoring here mirrors what the detector will do at serve time — rolling window over
    non-zero days only — so the threshold is calibrated against the same quantity it
    will later be compared to.
    """
    if len(usable) < interval_days + MIN_BACKTEST_WINDOWS:
        logger.debug("Not enough history to backtest a threshold; using floor %.2f", THRESHOLD_FLOOR)
        return THRESHOLD_FLOOR

    values = usable.sort_values("date_id")[metric].to_numpy()
    out_of_band = (values < lower_bound) | (values > upper_bound)
    ratios = pd.Series(out_of_band).rolling(interval_days).mean().dropna().to_numpy()
    if len(ratios) < MIN_BACKTEST_WINDOWS:
        return THRESHOLD_FLOOR

    threshold = float(np.percentile(ratios, 100.0 * (1.0 - target_flag_rate)))
    return float(min(max(threshold, THRESHOLD_FLOOR), THRESHOLD_CEILING))


def fit_one_location(
    history: pd.DataFrame,
    metric: str,
    recent_records: int = DEFAULT_RECENT_RECORDS,
    interval_days: int = DEFAULT_INTERVAL_DAYS,
    target_flag_rate: float = DEFAULT_TARGET_FLAG_RATE,
) -> dict:
    """
    Derive bounds, status and threshold from a location's most recent `recent_records`
    usable observations.

    Pure function over a DataFrame — no DB access — so the gating rules can be tested
    directly.

    Returns:
        dict with keys lower_bound, upper_bound, anomaly_threshold, status,
        fit_sample_size, fit_start_date_id and fit_end_date_id. The two dates describe
        the span the retained records actually cover, which differs per location and is
        wider than `recent_records` days wherever zero-days were skipped. lower_bound
        and upper_bound are None whenever status is not OK, since there are no
        meaningful bounds to record in those cases.
    """
    usable = _usable_rows(history, metric).sort_values("date_id")
    if recent_records:
        usable = usable.tail(recent_records)

    sample_size = len(usable)
    fit_start_date_id = int(usable["date_id"].iloc[0]) if sample_size else None
    fit_end_date_id = int(usable["date_id"].iloc[-1]) if sample_size else None

    def _rejected(status: str) -> dict:
        return {
            "lower_bound": None,
            "upper_bound": None,
            "anomaly_threshold": THRESHOLD_FLOOR,  # unused: status != OK short-circuits
            "status": status,
            "fit_sample_size": sample_size,
            "fit_start_date_id": fit_start_date_id,
            "fit_end_date_id": fit_end_date_id,
        }

    if sample_size == 0:
        return _rejected(STATUS_NO_DATA)
    if sample_size < MIN_FIT_SAMPLE:
        return _rejected(STATUS_INSUFFICIENT)

    values = usable[metric]
    lower_bound = float(np.percentile(values, LOWER_PERCENTILE))
    upper_bound = float(np.percentile(values, UPPER_PERCENTILE))

    if lower_bound == upper_bound:
        return _rejected(STATUS_FLAT)

    if metric == "ship_cnt" and upper_bound <= MIN_COUNT_UPPER_BOUND:
        return _rejected(STATUS_INSUFFICIENT)

    if metric == "duration" and usable["ship_cnt"].median() < MIN_DURATION_SAMPLE_SHIPS:
        # Too few ships per day for a daily mean transit time to mean anything.
        return _rejected(STATUS_INSUFFICIENT)

    threshold = _derive_threshold(
        usable=usable,
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
    }


def _next_date_id(date_id: int) -> int:
    """YYYYMMDD -> the following day, as YYYYMMDD."""
    return int((datetime.strptime(str(date_id), "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d"))


def _previous_date_id(date_id: int) -> int:
    """YYYYMMDD -> the preceding day, as YYYYMMDD."""
    return int((datetime.strptime(str(date_id), "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d"))


def _is_locked(conn: sqlite3.Connection, location_type: str, location_name: str, metric: str) -> bool:
    """True when a manually-set row is currently in force for this key."""
    row = conn.execute(
        f"""
        SELECT 1 FROM {PARAM_TABLE}
        WHERE location_type = ? AND location_name = ? AND metric = ?
          AND valid_to_date_id IS NULL AND is_locked = 1
        LIMIT 1
        """,
        (location_type, location_name, metric),
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
    """Close out the in-force row and insert the new one, inside the caller's transaction."""
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # Retire whatever is currently in force, so exactly one row applies to any date.
    conn.execute(
        f"""
        UPDATE {PARAM_TABLE}
        SET valid_to_date_id = ?, updated_timestamp_utc = ?
        WHERE location_type = ? AND location_name = ? AND metric = ?
          AND valid_to_date_id IS NULL
          AND valid_from_date_id < ?
        """,
        (_previous_date_id(valid_from), updated_at, location_type, location_name, metric, valid_from),
    )

    # ON CONFLICT rather than a plain INSERT so re-running the same fit is idempotent.
    conn.execute(
        f"""
        INSERT INTO {PARAM_TABLE} (
            location_type, location_name, metric, valid_from_date_id, valid_to_date_id,
            lower_bound, upper_bound, anomaly_threshold, interval_days, status,
            fit_method, fit_start_date_id, fit_end_date_id, fit_sample_size,
            is_locked, updated_timestamp_utc
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(location_type, location_name, metric, valid_from_date_id) DO UPDATE SET
            valid_to_date_id      = NULL,
            lower_bound           = excluded.lower_bound,
            upper_bound           = excluded.upper_bound,
            anomaly_threshold     = excluded.anomaly_threshold,
            interval_days         = excluded.interval_days,
            status                = excluded.status,
            fit_method            = excluded.fit_method,
            fit_start_date_id     = excluded.fit_start_date_id,
            fit_end_date_id       = excluded.fit_end_date_id,
            fit_sample_size       = excluded.fit_sample_size,
            updated_timestamp_utc = excluded.updated_timestamp_utc
        """,
        (
            location_type, location_name, metric, valid_from,
            fitted["lower_bound"], fitted["upper_bound"], fitted["anomaly_threshold"],
            interval_days, fitted["status"],
            FIT_METHOD_PERCENTILE,
            fitted["fit_start_date_id"], fitted["fit_end_date_id"], fitted["fit_sample_size"],
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
    persist: bool = True,
    engine=None,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """
    Fit detection parameters for every location of one type and write them to
    m_roll_percentile_parameter.

    Each location is fitted on its own most recent `recent_records` usable (non-zero)
    observations, so the calendar span behind a fit varies by location: a busy strait
    reaches back about that many days, a quiet port reaches back further. The span
    actually used is recorded per row in fit_start_date_id / fit_end_date_id.

    Args:
        location_type   : 'pipe' or 'port'.
        metric          : 'ship_cnt' or 'duration'.
        recent_records  : how many usable observations to fit on, counting back from
                          as_of_date_id. Pass 0 to use everything available.
        as_of_date_id   : YYYYMMDD; ignore data after this date. Defaults to the latest
                          date present in the source table. The fitted rows take effect
                          the day after.
        fit_start       : optional YYYYMMDD floor, to stop a sparse location reaching
                          back across a known regime break.
        interval_days   : detection window the threshold is calibrated for.
        target_flag_rate: share of windows the threshold should leave flagged over the
                          fit sample.
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
            if persist and _is_locked(conn, location_type, location_name, metric):
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

            history = _load_history(
                spec["table"], spec["key_col"], location_name, as_of_date_id, engine, fit_start
            )
            fitted = fit_one_location(
                history=history,
                metric=metric,
                recent_records=recent_records,
                interval_days=interval_days,
                target_flag_rate=target_flag_rate,
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
                **fitted,
            })
            logger.info(
                "%s/%s/%s: status=%s bounds=[%s, %s] threshold=%s n=%d span=%s-%s",
                location_type, location_name, metric, fitted["status"],
                fitted["lower_bound"], fitted["upper_bound"],
                fitted["anomaly_threshold"], fitted["fit_sample_size"],
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
