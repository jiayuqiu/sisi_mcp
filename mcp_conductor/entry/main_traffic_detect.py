"""
Run rolling percentile traffic anomaly detection across pipes and ports,
persist results to m_pipe_anomaly_roll_percentile, and refresh the monitoring
snapshot.
"""
import argparse
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mcp_conductor.detector.detect_engine import rp_detect_engine
from mcp_conductor.detector.roll_percentile.monitor import monitor_roll_percentile
from mcp_conductor.resources.utils.db import get_engine
from mcp_conductor.resources.utils.logger import get_logger


logger = get_logger(__name__)

DB_PATH = Path("./data/sisi.sqlite")


def load_pipe_data(pipe_name: str) -> pd.DataFrame:
    """Load full historical ship count data for a strait from SQLite."""
    df = pd.read_sql(
        "SELECT date_id, ship_cnt FROM ship_cnt_in_pipe WHERE pipe_name = :name",
        con=get_engine(),
        params={"name": pipe_name},
    )
    return df


def save_anomaly_results(app_anomaly_results: dict) -> None:
    """
    Persist detection results into m_pipe_anomaly_roll_percentile.

    Uses INSERT OR REPLACE so re-running detection on the same date
    overwrites the previous result.

    Args:
        app_anomaly_results: output of pipe_detect_engine — location results including
                           the legacy anomaly ratio and directional count ratios.
    """
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    with sqlite3.connect(str(DB_PATH)) as conn:
        for app_type, anamaly_result in app_anomaly_results.items():
            if app_type == "pipe":
                pass
            elif app_type == "port":
                pass
            else:
                raise ValueError(f"app_type only supports `pipe` or `port`, current value is {app_type}")

            for row in anamaly_result:
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO m_pipe_anomaly_roll_percentile
                            (location_type, pipe_name, date_id, anomaly_flag, quantile_10, quantile_25,
                             quantile_75, quantile_90, anomaly_ratio, ratio_low,
                             ratio_high, direction, duration_anomaly_flag,
                             duration_quantile_10, duration_quantile_25,
                             duration_quantile_75, duration_quantile_90,
                             duration_anomaly_ratio, duration_ratio_low,
                             duration_ratio_high, duration_direction, duration_status,
                             regime, updated_timestamp_utc)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            app_type,
                            row[app_type],
                            row["run_date_id"],
                            int(row["anomaly_flag"]),
                            row["quantile_10"],
                            row["quantile_25"],
                            row["quantile_75"],
                            row["quantile_90"],
                            row["anomaly_ratio"],
                            row["ratio_low"],
                            row["ratio_high"],
                            row["direction"],
                            row.get("duration_anomaly_flag"),
                            row.get("duration_quantile_10"),
                            row.get("duration_quantile_25"),
                            row.get("duration_quantile_75"),
                            row.get("duration_quantile_90"),
                            row.get("duration_anomaly_ratio"),
                            row.get("duration_ratio_low"),
                            row.get("duration_ratio_high"),
                            row.get("duration_direction"),
                            row.get("duration_status"),
                            row.get("regime"),
                            updated_at,
                        ),
                    )
                except Exception:
                    logger.error("[%s] FAILED to save row: %s", row.get("run_date_id"), row, exc_info=True)
                    raise
            conn.commit()
            logger.info("Saved %d anomaly results to m_pipe_anomaly_roll_percentile.", len(anamaly_result))


def traffic_detect(run_date: str) -> None:
    """
    Run rolling percentile detection across all straits for a given date
    and persist the results to m_pipe_anomaly_roll_percentile.

    Args:
        run_date     : detection date in YYYY-MM-DD format.
    """
    # detect anomalies across all straits
    app_anomaly_list = rp_detect_engine(run_date=run_date)

    # persist results
    save_anomaly_results(app_anomaly_list)

    # Monitoring runs after persistence so the snapshot always includes this date's
    # corrected-threshold results. Re-running the date updates the same snapshot.
    monitor_roll_percentile(
        db_path=DB_PATH,
        end_date_id=run_date,
        persist=True,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Run rolling percentile traffic detection")
    parser.add_argument("--run-date", type=str, required=True, help="Detection date (YYYY-MM-DD)")
    args = parser.parse_args()
    run_date = args.run_date

    # trigger detect
    traffic_detect(run_date)
