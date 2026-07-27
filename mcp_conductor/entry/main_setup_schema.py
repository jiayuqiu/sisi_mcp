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
    pipe_name              TEXT,
    date_id                INTEGER,  -- YYYYMMDD format
    anomaly_flag           INTEGER,  -- FK to dim_anomaly_flag.flag_value
    quantile_10            REAL,
    quantile_25            REAL,
    quantile_75            REAL,
    quantile_90            REAL,
    anomaly_ratio          REAL,     -- outlier days / interval_days
    updated_timestamp_utc  TEXT,     -- ISO-8601, UTC (e.g. 2024-04-05T12:00:00)
    PRIMARY KEY (pipe_name, date_id)
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

    fit_method             TEXT NOT NULL,     -- 'percentile_10_90' | 'manual'
    fit_start_date_id      INTEGER,           -- fitting window, recorded to spot regime breaks
    fit_end_date_id        INTEGER,
    fit_sample_size        INTEGER,           -- nonzero days actually used
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
    m.updated_timestamp_utc
FROM m_pipe_anomaly_roll_percentile m
LEFT JOIN dim_anomaly_flag d ON m.anomaly_flag = d.flag_value;
"""


def setup_schema() -> None:
    """Ensure the SQLite database and all required tables exist."""
    if not DB_PATH.exists():
        logger.warning("sisi.sqlite not found at %s — it will be created.", DB_PATH.absolute())

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(SQL_CREATE_SHIP_CNT_IN_PIPE)
        logger.info("Table ship_cnt_in_pipe: ready.")

        conn.execute(SQL_CREATE_SHIP_CNT_IN_PORT)
        logger.info("Table ship_cnt_in_port: ready.")

        conn.execute(SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        logger.info("Table m_pipe_anomaly_roll_percentile: ready.")

        conn.execute(SQL_CREATE_M_ROLL_PERCENTILE_PARAMETER)
        logger.info("Table m_roll_percentile_parameter: ready.")

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
