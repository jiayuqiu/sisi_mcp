import sqlite3
import logging
import os
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path

# Ensure we can import from mcp_conductor if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path("./data/sisi.sqlite")

SQL_CREATE_SHIP_CNT_IN_PIPE = """
CREATE TABLE IF NOT EXISTS ship_cnt_in_pipe (
    pipe_name      TEXT,
    date_id        INTEGER,  -- YYYYMMDD format
    ship_cnt       INTEGER,  -- count of ship passing the strait
    duration       REAL,     -- time of ship passing the strait
    detection_flag TEXT,     -- reserved, unused
    PRIMARY KEY (pipe_name, date_id)
);
"""

SQL_CREATE_SHIP_CNT_IN_PORT = """
CREATE TABLE IF NOT EXISTS ship_cnt_in_port (
    port_name      TEXT,
    date_id        INTEGER,  -- YYYYMMDD format
    ship_cnt       INTEGER,  -- count of ship berthing in the port
    duration       REAL,     -- time of ship berthing in the port
    detection_flag TEXT,     -- reserved, unused
    PRIMARY KEY (port_name, date_id)
);
"""

SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE = """
CREATE TABLE IF NOT EXISTS m_pipe_anomaly_roll_percentile (
    location_type          TEXT NOT NULL CHECK (location_type IN ('pipe', 'port')),
    pipe_name              TEXT,     -- compatibility name; may identify a pipe or port
    date_id                INTEGER,  -- YYYYMMDD format
    anomaly_flag           INTEGER,  -- FK to dim_anomaly_flag.flag_value
    quantile_10            REAL,
    quantile_25            REAL,
    quantile_75            REAL,
    quantile_90            REAL,
    anomaly_ratio          REAL,     -- legacy: all outlier days / interval_days
    ratio_low              REAL,     -- days below lower bound / interval_days
    ratio_high             REAL,     -- days above upper bound / interval_days
    direction              TEXT,     -- NORMAL | LOW | HIGH | MIXED | UNKNOWN
    duration_anomaly_flag  INTEGER,  -- duration-channel FK to dim_anomaly_flag.flag_value
    duration_quantile_10   REAL,
    duration_quantile_25   REAL,
    duration_quantile_75   REAL,
    duration_quantile_90   REAL,
    duration_anomaly_ratio REAL,
    duration_ratio_low     REAL,
    duration_ratio_high    REAL,
    duration_direction     TEXT,     -- NORMAL | LOW | HIGH | MIXED | UNKNOWN
    duration_status        TEXT,     -- OK | NO_DATA | NO_PARAMETERS | fitted rejection status
    regime                 TEXT,     -- combined count/duration classification
    updated_timestamp_utc  TEXT,     -- ISO-8601, UTC (e.g. 2024-04-05T12:00:00)
    PRIMARY KEY (location_type, pipe_name, date_id)
);
"""

SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER = """
CREATE TABLE IF NOT EXISTS m_roll_percentile_parameter (
    location_type          TEXT NOT NULL,     -- 'pipe' | 'port'
    location_name          TEXT NOT NULL,
    metric                 TEXT NOT NULL,     -- 'ship_cnt' | 'duration'
    valid_from_date_id     INTEGER NOT NULL,  -- YYYYMMDD, first date this row applies to
    valid_to_date_id       INTEGER,           -- YYYYMMDD, NULL = currently in force

    lower_bound            REAL,              -- NULL when status <> 'OK'
    upper_bound            REAL,
    anomaly_threshold      REAL NOT NULL,     -- per-location: the null ratio varies 0.20-0.60
    interval_days          INTEGER NOT NULL DEFAULT 30,
    status                 TEXT NOT NULL,     -- 'OK' | 'FLAT' | 'INSUFFICIENT' | 'NO_DATA'

    fit_method             TEXT NOT NULL,     -- 'percentile_10_90_holdout' | 'manual'
    fit_start_date_id      INTEGER,           -- fitting window, recorded to spot regime breaks
    fit_end_date_id        INTEGER,
    fit_sample_size        INTEGER,           -- positive training + scoring validation rows retained
    training_sample_size   INTEGER,           -- earlier observations used to fit bounds
    calibration_start_date_id INTEGER,        -- chronological holdout provenance
    calibration_end_date_id INTEGER,
    calibration_sample_size INTEGER,
    calibration_target_flag_rate REAL,
    calibration_flag_rate REAL,               -- realized holdout windows above threshold
    is_locked              INTEGER NOT NULL DEFAULT 0,  -- 1 = refit job must not overwrite
    updated_timestamp_utc  TEXT,              -- ISO-8601, UTC

    PRIMARY KEY (location_type, location_name, metric, valid_from_date_id)
);
"""

SQL_CREATE_DIM_ANOMALY_FLAG = """
CREATE TABLE IF NOT EXISTS dim_anomaly_flag (
    flag_value   INTEGER PRIMARY KEY,
    flag_name    TEXT NOT NULL,
    description  TEXT
);
"""

SQL_CREATE_M_ROLL_PERCENTILE_MONITOR = """
CREATE TABLE IF NOT EXISTS m_roll_percentile_monitor (
    snapshot_date_id         INTEGER NOT NULL,
    window_start_date_id     INTEGER NOT NULL,
    window_end_date_id       INTEGER NOT NULL,
    location_type            TEXT NOT NULL,
    location_name            TEXT NOT NULL,
    metric                   TEXT NOT NULL,
    direction                TEXT NOT NULL,  -- 'ANY' | 'LOW' | 'HIGH' | 'MIXED'
    parameter_valid_from_date_id INTEGER NOT NULL,
    anomaly_threshold        REAL,
    target_flag_rate         REAL NOT NULL,
    alert_flag_rate          REAL NOT NULL,
    observation_count        INTEGER NOT NULL,
    eligible_count           INTEGER NOT NULL,
    flagged_count            INTEGER NOT NULL,
    flag_rate                REAL,
    status                   TEXT NOT NULL,  -- OK | WARMING_UP | ELEVATED | NO_DATA | ...
    updated_timestamp_utc    TEXT NOT NULL,
    PRIMARY KEY (
        snapshot_date_id, location_type, location_name, metric, direction
    )
);
"""

SQL_CREATE_LOG_AGENT_WORKLOG = """
CREATE TABLE IF NOT EXISTS log_agent_worklog (
    return_id TEXT UNIQUE NOT NULL,
    question_type TEXT,
    full_response TEXT,
    payload TEXT,
    date_id INT,
    pipe_name TEXT,
    run_timestamp TEXT DEFAULT (datetime('now')),
    content TEXT,
    reasoning_content TEXT,
    PRIMARY KEY (pipe_name, date_id, run_timestamp)
);
"""

SQL_DROP_VW_M_PIPE_ANOMALY_ROLL_PERCENTILE = """
DROP VIEW IF EXISTS vw_m_pipe_anomaly_roll_percentile;
"""

SQL_CREATE_VW_M_PIPE_ANOMALY_ROLL_PERCENTILE = """
CREATE VIEW vw_m_pipe_anomaly_roll_percentile AS
SELECT
    m.location_type,
    m.pipe_name,
    m.date_id,
    m.anomaly_flag,
    d.flag_name,
    d.description,
    m.quantile_10,
    m.quantile_25,
    m.quantile_75,
    m.quantile_90,
    m.anomaly_ratio,
    m.ratio_low,
    m.ratio_high,
    m.direction,
    m.duration_anomaly_flag,
    m.duration_quantile_10,
    m.duration_quantile_25,
    m.duration_quantile_75,
    m.duration_quantile_90,
    m.duration_anomaly_ratio,
    m.duration_ratio_low,
    m.duration_ratio_high,
    m.duration_direction,
    m.duration_status,
    m.regime,
    m.updated_timestamp_utc
FROM m_pipe_anomaly_roll_percentile m
LEFT JOIN dim_anomaly_flag d ON m.anomaly_flag = d.flag_value;
"""

M_PIPE_ANOMALY_RESULT_COLUMNS = {
    "ratio_low": "REAL",
    "ratio_high": "REAL",
    "direction": "TEXT",
    "duration_anomaly_flag": "INTEGER",
    "duration_quantile_10": "REAL",
    "duration_quantile_25": "REAL",
    "duration_quantile_75": "REAL",
    "duration_quantile_90": "REAL",
    "duration_anomaly_ratio": "REAL",
    "duration_ratio_low": "REAL",
    "duration_ratio_high": "REAL",
    "duration_direction": "TEXT",
    "duration_status": "TEXT",
    "regime": "TEXT",
}

M_ROLL_PERCENTILE_PARAMETER_COLUMNS = {
    "training_sample_size": "INTEGER",
    "calibration_start_date_id": "INTEGER",
    "calibration_end_date_id": "INTEGER",
    "calibration_sample_size": "INTEGER",
    "calibration_target_flag_rate": "REAL",
    "calibration_flag_rate": "REAL",
}

SHIP_METRIC_COLUMNS = {
    "duration": "REAL",
}


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    """Add missing nullable columns to an existing SQLite table."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")


def _migrate_anomaly_result_identity(conn: sqlite3.Connection) -> None:
    """Key anomaly results by location type, name, and date.

    SQLite cannot alter a primary key in place, so legacy tables are rebuilt. Existing
    rows are classified from the source catalogs. A name present in both catalogs is
    rejected because the legacy row does not contain enough information to classify it
    safely. Source-less legacy rows default to ``pipe`` for backward compatibility.
    """
    table = "m_pipe_anomaly_roll_percentile"
    table_info = list(conn.execute(f"PRAGMA table_info({table})"))
    if not table_info:
        conn.execute(SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        return

    primary_key = [
        row[1]
        for row in sorted((row for row in table_info if row[5]), key=lambda row: row[5])
    ]
    if primary_key == ["location_type", "pipe_name", "date_id"]:
        return

    ambiguous = conn.execute(
        f"""
        SELECT DISTINCT r.pipe_name
        FROM {table} r
        JOIN ship_cnt_in_pipe p ON p.pipe_name = r.pipe_name
        JOIN ship_cnt_in_port o ON o.port_name = r.pipe_name
        LIMIT 1
        """
    ).fetchone()
    if ambiguous:
        raise ValueError(
            "Cannot migrate anomaly results because a legacy name exists as both "
            f"pipe and port: {ambiguous[0]}"
        )

    # Bring every legacy result table to the widened column set before copying it.
    _ensure_columns(conn, table, M_PIPE_ANOMALY_RESULT_COLUMNS)
    legacy_columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    # Preserve the legacy table's column ordering explicitly, then rebuild under the
    # canonical schema.
    result_columns = [column for column in legacy_columns if column != "location_type"]

    conn.execute(SQL_DROP_VW_M_PIPE_ANOMALY_ROLL_PERCENTILE)
    conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy_identity")
    conn.execute(SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE)

    legacy_location_expression = (
        "COALESCE(r.location_type, " if "location_type" in legacy_columns else ""
    )
    inferred_location_expression = """
        CASE
            WHEN EXISTS (
                SELECT 1 FROM ship_cnt_in_port o WHERE o.port_name = r.pipe_name
            ) THEN 'port'
            ELSE 'pipe'
        END
    """
    if legacy_location_expression:
        inferred_location_expression = (
            legacy_location_expression + inferred_location_expression + ")"
        )

    column_sql = ", ".join(result_columns)
    select_sql = ", ".join(f"r.{column}" for column in result_columns)
    conn.execute(
        f"""
        INSERT INTO {table} (location_type, {column_sql})
        SELECT {inferred_location_expression}, {select_sql}
        FROM {table}_legacy_identity r
        """
    )
    conn.execute(f"DROP TABLE {table}_legacy_identity")


def setup_schema() -> None:
    """Ensure the SQLite database and all required tables exist."""
    if not DB_PATH.exists():
        logger.warning("sisi.sqlite not found at %s — it will be created.", DB_PATH.absolute())

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(SQL_CREATE_SHIP_CNT_IN_PIPE)
        _ensure_columns(conn, "ship_cnt_in_pipe", SHIP_METRIC_COLUMNS)
        logger.info("Table ship_cnt_in_pipe: ready.")

        conn.execute(SQL_CREATE_SHIP_CNT_IN_PORT)
        _ensure_columns(conn, "ship_cnt_in_port", SHIP_METRIC_COLUMNS)
        logger.info("Table ship_cnt_in_port: ready.")

        conn.execute(SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        _ensure_columns(
            conn,
            "m_pipe_anomaly_roll_percentile",
            M_PIPE_ANOMALY_RESULT_COLUMNS,
        )
        _migrate_anomaly_result_identity(conn)
        logger.info("Table m_pipe_anomaly_roll_percentile: ready.")

        conn.execute(SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER)
        _ensure_columns(
            conn,
            "m_roll_percentile_parameter",
            M_ROLL_PERCENTILE_PARAMETER_COLUMNS,
        )
        logger.info("Table m_roll_percentile_parameter: ready.")

        conn.execute(SQL_CREATE_M_ROLL_PERCENTILE_MONITOR)
        logger.info("Table m_roll_percentile_monitor: ready.")

        conn.execute(SQL_CREATE_DIM_ANOMALY_FLAG)
        for f in dataclass_fields(ROLLING_PERCENTILE_FLAG):
            conn.execute(
                "INSERT OR REPLACE INTO dim_anomaly_flag (flag_value, flag_name, description) VALUES (?, ?, ?)",
                (getattr(ROLLING_PERCENTILE_FLAG, f.name), f.name, f.metadata.get("description", "")),
            )
        logger.info("Table dim_anomaly_flag: ready.")

        conn.execute(SQL_CREATE_LOG_AGENT_WORKLOG)
        logger.info("Table log_agent_worklog: ready.")

        conn.execute(SQL_DROP_VW_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        conn.execute(SQL_CREATE_VW_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        logger.info("View vw_m_pipe_anomaly_roll_percentile: ready.")

        conn.commit()


if __name__ == "__main__":
    setup_schema()
