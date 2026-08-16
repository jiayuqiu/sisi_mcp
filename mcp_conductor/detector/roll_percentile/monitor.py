"""Monitor live anomaly rates produced by the effective rolling-percentile parameters."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from mcp_conductor.resources.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path("./data/sisi.sqlite")
MONITOR_TABLE = "m_roll_percentile_monitor"

MONITOR_DIRECTIONS = ("ANY", "LOW", "HIGH", "MIXED")
DEFAULT_WINDOW_DAYS = 30
DEFAULT_MIN_ELIGIBLE_SAMPLES = 30
DEFAULT_TARGET_FLAG_RATE = 0.05
DEFAULT_ALERT_FLAG_RATE = 0.10
DEFAULT_ALERT_MULTIPLIER = 2.0

STATUS_OK = "OK"
STATUS_WARMING_UP = "WARMING_UP"
STATUS_ELEVATED = "ELEVATED"
STATUS_NO_DATA = "NO_DATA"
STATUS_NO_ELIGIBLE_DATA = "NO_ELIGIBLE_DATA"
STATUS_PARAMETER_UNUSABLE = "PARAMETER_UNUSABLE"


def _date_id(value: str | int) -> int:
    """Normalize YYYY-MM-DD or YYYYMMDD into an integer date id."""
    text = str(value).replace("-", "")
    parsed = datetime.strptime(text, "%Y%m%d")
    return int(parsed.strftime("%Y%m%d"))


def _window_start(end_date_id: int, window_days: int) -> int:
    end = datetime.strptime(str(end_date_id), "%Y%m%d")
    return int((end - timedelta(days=window_days - 1)).strftime("%Y%m%d"))


def _latest_result_date(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(date_id) FROM m_pipe_anomaly_roll_percentile").fetchone()
    if not row or row[0] is None:
        raise ValueError("m_pipe_anomaly_roll_percentile is empty; nothing to monitor.")
    return int(row[0])


def _load_effective_parameters(conn: sqlite3.Connection, end_date_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        WITH ranked AS (
            SELECT
                location_type,
                location_name,
                metric,
                valid_from_date_id,
                anomaly_threshold,
                calibration_target_flag_rate,
                status AS parameter_status,
                ROW_NUMBER() OVER (
                    PARTITION BY location_type, location_name, metric
                    ORDER BY valid_from_date_id DESC
                ) AS row_number
            FROM m_roll_percentile_parameter
            WHERE valid_from_date_id <= :end_date_id
              AND (valid_to_date_id IS NULL OR valid_to_date_id >= :end_date_id)
        )
        SELECT * FROM ranked WHERE row_number = 1
        """,
        conn,
        params={"end_date_id": end_date_id},
    )


def _load_results(
    conn: sqlite3.Connection,
    start_date_id: int,
    end_date_id: int,
) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            r.location_type,
            r.pipe_name AS location_name,
            r.date_id,
            'ship_cnt' AS metric,
            r.anomaly_flag,
            r.direction,
            NULL AS channel_status
        FROM m_pipe_anomaly_roll_percentile r
        WHERE r.date_id BETWEEN :start_date_id AND :end_date_id

        UNION ALL

        SELECT
            r.location_type,
            r.pipe_name AS location_name,
            r.date_id,
            'duration' AS metric,
            r.duration_anomaly_flag AS anomaly_flag,
            r.duration_direction AS direction,
            r.duration_status AS channel_status
        FROM m_pipe_anomaly_roll_percentile r
        WHERE r.date_id BETWEEN :start_date_id AND :end_date_id
        """,
        conn,
        params={"start_date_id": start_date_id, "end_date_id": end_date_id},
    )


def build_monitor_snapshot(
    conn: sqlite3.Connection,
    end_date_id: int | str,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_eligible_samples: int = DEFAULT_MIN_ELIGIBLE_SAMPLES,
    alert_flag_rate: float | None = None,
) -> list[dict]:
    """Calculate per-location, metric, and anomaly-direction flag rates.

    Only result dates on or after the current parameter's ``valid_from_date_id`` are
    eligible. This prevents a newly corrected threshold from being evaluated against
    detections produced by an older parameter version.
    """
    if window_days <= 0:
        raise ValueError(f"window_days must be > 0, got {window_days}")
    if min_eligible_samples <= 0:
        raise ValueError(
            f"min_eligible_samples must be > 0, got {min_eligible_samples}"
        )
    if alert_flag_rate is not None and not 0 <= alert_flag_rate <= 1:
        raise ValueError(f"alert_flag_rate must be between 0 and 1, got {alert_flag_rate}")

    end_date_id = _date_id(end_date_id)
    requested_start_date_id = _window_start(end_date_id, window_days)
    parameters = _load_effective_parameters(conn, end_date_id)
    results = _load_results(conn, requested_start_date_id, end_date_id)
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    snapshots: list[dict] = []
    for parameter in parameters.itertuples(index=False):
        effective_start_date_id = max(
            requested_start_date_id,
            int(parameter.valid_from_date_id),
        )
        selected = results[
            (results["location_type"] == parameter.location_type)
            & (results["location_name"] == parameter.location_name)
            & (results["metric"] == parameter.metric)
            & (results["date_id"] >= effective_start_date_id)
        ]

        parameter_ok = parameter.parameter_status == "OK"
        eligible = selected[selected["anomaly_flag"].isin([0, 1])] if parameter_ok else selected.iloc[0:0]
        if parameter.metric == "duration":
            eligible = eligible[eligible["channel_status"] == "OK"]

        target_rate = (
            float(parameter.calibration_target_flag_rate)
            if pd.notna(parameter.calibration_target_flag_rate)
            else DEFAULT_TARGET_FLAG_RATE
        )
        effective_alert_rate = (
            float(alert_flag_rate)
            if alert_flag_rate is not None
            else max(DEFAULT_ALERT_FLAG_RATE, target_rate * DEFAULT_ALERT_MULTIPLIER)
        )

        for direction in MONITOR_DIRECTIONS:
            if direction == "ANY":
                flagged = eligible[eligible["anomaly_flag"] == 1]
            else:
                flagged = eligible[
                    (eligible["anomaly_flag"] == 1)
                    & (eligible["direction"] == direction)
                ]

            observation_count = len(selected)
            eligible_count = len(eligible)
            flagged_count = len(flagged)
            flag_rate = flagged_count / eligible_count if eligible_count else None

            if not parameter_ok:
                status = STATUS_PARAMETER_UNUSABLE
            elif observation_count == 0:
                status = STATUS_NO_DATA
            elif eligible_count == 0:
                status = STATUS_NO_ELIGIBLE_DATA
            elif eligible_count < min_eligible_samples:
                status = STATUS_WARMING_UP
            elif flag_rate is not None and flag_rate > effective_alert_rate:
                status = STATUS_ELEVATED
            else:
                status = STATUS_OK

            snapshots.append(
                {
                    "snapshot_date_id": end_date_id,
                    "window_start_date_id": effective_start_date_id,
                    "window_end_date_id": end_date_id,
                    "location_type": parameter.location_type,
                    "location_name": parameter.location_name,
                    "metric": parameter.metric,
                    "direction": direction,
                    "parameter_valid_from_date_id": int(parameter.valid_from_date_id),
                    "anomaly_threshold": (
                        float(parameter.anomaly_threshold)
                        if pd.notna(parameter.anomaly_threshold)
                        else None
                    ),
                    "target_flag_rate": target_rate,
                    "alert_flag_rate": effective_alert_rate,
                    "observation_count": observation_count,
                    "eligible_count": eligible_count,
                    "flagged_count": flagged_count,
                    "flag_rate": flag_rate,
                    "status": status,
                    "updated_timestamp_utc": updated_at,
                }
            )

    return snapshots


def persist_monitor_snapshot(conn: sqlite3.Connection, snapshots: list[dict]) -> None:
    """Upsert a monitoring snapshot; rerunning one date is idempotent."""
    conn.executemany(
        f"""
        INSERT INTO {MONITOR_TABLE} (
            snapshot_date_id, window_start_date_id, window_end_date_id,
            location_type, location_name, metric, direction,
            parameter_valid_from_date_id, anomaly_threshold, target_flag_rate,
            alert_flag_rate, observation_count, eligible_count, flagged_count,
            flag_rate, status, updated_timestamp_utc
        ) VALUES (
            :snapshot_date_id, :window_start_date_id, :window_end_date_id,
            :location_type, :location_name, :metric, :direction,
            :parameter_valid_from_date_id, :anomaly_threshold, :target_flag_rate,
            :alert_flag_rate, :observation_count, :eligible_count, :flagged_count,
            :flag_rate, :status, :updated_timestamp_utc
        )
        ON CONFLICT(snapshot_date_id, location_type, location_name, metric, direction)
        DO UPDATE SET
            window_start_date_id = excluded.window_start_date_id,
            window_end_date_id = excluded.window_end_date_id,
            parameter_valid_from_date_id = excluded.parameter_valid_from_date_id,
            anomaly_threshold = excluded.anomaly_threshold,
            target_flag_rate = excluded.target_flag_rate,
            alert_flag_rate = excluded.alert_flag_rate,
            observation_count = excluded.observation_count,
            eligible_count = excluded.eligible_count,
            flagged_count = excluded.flagged_count,
            flag_rate = excluded.flag_rate,
            status = excluded.status,
            updated_timestamp_utc = excluded.updated_timestamp_utc
        """,
        snapshots,
    )
    conn.commit()


def monitor_roll_percentile(
    db_path: Path = DB_PATH,
    end_date_id: int | str | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_eligible_samples: int = DEFAULT_MIN_ELIGIBLE_SAMPLES,
    alert_flag_rate: float | None = None,
    persist: bool = True,
) -> list[dict]:
    """Build and optionally persist one corrected-threshold monitoring snapshot."""
    with sqlite3.connect(db_path) as conn:
        if end_date_id is None:
            end_date_id = _latest_result_date(conn)
        snapshots = build_monitor_snapshot(
            conn=conn,
            end_date_id=end_date_id,
            window_days=window_days,
            min_eligible_samples=min_eligible_samples,
            alert_flag_rate=alert_flag_rate,
        )
        if persist:
            persist_monitor_snapshot(conn, snapshots)

    logger.info(
        "Monitoring snapshot %s: %d rows, %d elevated, %d warming up.%s",
        _date_id(end_date_id),
        len(snapshots),
        sum(1 for row in snapshots if row["status"] == STATUS_ELEVATED),
        sum(1 for row in snapshots if row["status"] == STATUS_WARMING_UP),
        " (dry run — nothing written)" if not persist else "",
    )
    return snapshots
