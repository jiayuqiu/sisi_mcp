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
    ship_cnt       INTEGER,
    detection_flag TEXT,     -- reserved, unused
    PRIMARY KEY (pipe_name, date_id)
);
"""

SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE = """
CREATE TABLE IF NOT EXISTS m_pipe_anomaly_roll_percentile (
    pipe_name              TEXT,
    date_id                INTEGER,  -- YYYYMMDD format
    anomaly_flag           INTEGER PRIMARY KEY,  -- FK to dim_anomaly_flag.flag_value
    quantile_10            REAL,
    quantile_90            REAL,
    anomaly_ratio          REAL,     -- outlier days / interval_days
    updated_timestamp_utc  TEXT      -- ISO-8601, UTC (e.g. 2024-04-05T12:00:00)
);
"""

SQL_CREATE_DIM_ANOMALY_FLAG = """
CREATE TABLE IF NOT EXISTS dim_anomaly_flag (
    flag_value   INTEGER PRIMARY KEY,
    flag_name    TEXT NOT NULL,
    description  TEXT
);
"""

SQL_CREATE_VW_M_PIPE_ANOMALY_ROLL_PERCENTILE = """
CREATE VIEW IF NOT EXISTS vw_m_pipe_anomaly_roll_percentile AS
SELECT
    m.pipe_name,
    m.date_id,
    m.anomaly_flag,
    d.flag_name,
    d.description,
    m.quantile_10,
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

        conn.execute(SQL_CREATE_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        logger.info("Table m_pipe_anomaly_roll_percentile: ready.")

        conn.execute(SQL_CREATE_DIM_ANOMALY_FLAG)
        for f in dataclass_fields(ROLLING_PERCENTILE_FLAG):
            conn.execute(
                "INSERT OR REPLACE INTO dim_anomaly_flag (flag_value, flag_name, description) VALUES (?, ?, ?)",
                (getattr(ROLLING_PERCENTILE_FLAG, f.name), f.name, f.metadata.get("description", "")),
            )
        logger.info("Table dim_anomaly_flag: ready.")

        conn.execute(SQL_CREATE_VW_M_PIPE_ANOMALY_ROLL_PERCENTILE)
        logger.info("View vw_m_pipe_anomaly_roll_percentile: ready.")

        conn.commit()


if __name__ == "__main__":
    setup_schema()
