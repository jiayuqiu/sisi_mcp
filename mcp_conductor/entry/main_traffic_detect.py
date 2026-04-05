"""
Detect anomalous strait traffic using the rolling percentile method.
When an anomaly is found, query DeepSeek (web search) for weather and news
context around that date, then return the summary.
"""
import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mcp_conductor.resources.utils.db import get_engine
from mcp_conductor.resources.utils.logger import get_logger
from mcp_conductor.detector.pipe_detect_engine import pipe_rp_detect_engine
from mcp_conductor.resources.deepseek.rest_api import DeepSeekClient
from mcp_conductor.templates.questions import WEB_SEARCH_WEATHER_NEWS

logger = get_logger(__name__)

DB_PATH = Path("./data/sisi.sqlite")


def save_to_log(response: dict, payload: str, question_type: str = "weather_news") -> None:
    """Persist a DeepSeek API response to log_agent_work_history."""
    try:
        return_id = response.get("id", "")
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        reasoning_content = response.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
        full_response = json.dumps(response, ensure_ascii=False)

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT INTO log_agent_work_history
               (return_id, question_type, full_response, payload, content, reasoning_content)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (return_id, question_type, full_response, payload, content, reasoning_content),
        )
        conn.commit()
        conn.close()
        logger.info("Saved log for return_id=%s", return_id)
    except Exception as e:
        logger.error("Failed to save log: %s", e)


def load_pipe_data(pipe_name: str) -> pd.DataFrame:
    """Load full historical ship count data for a strait from SQLite."""
    df = pd.read_sql(
        "SELECT date_id, ship_cnt FROM ship_cnt_in_pipe WHERE pipe_name = :name",
        con=get_engine(),
        params={"name": pipe_name},
    )
    return df


def analyze_congestion(pipe_name: str, run_date: str) -> str:
    """Query DeepSeek for weather/news context on the anomaly date."""
    run_date_id = int(run_date.replace("-", ""))
    ds_client = DeepSeekClient()

    question = WEB_SEARCH_WEATHER_NEWS.format(date_id=run_date_id, pipe_name=pipe_name)
    response = ds_client.search_and_ask(question=question)
    logger.info("DeepSeek response: %s", response)

    save_to_log(response, payload=question, question_type="weather_news")
    return response["choices"][0]["message"]["content"]


def save_anomaly_results(pipe_anomaly_list: list[dict]) -> None:
    """
    Persist detection results into m_pipe_anomaly_roll_percentile.

    Uses INSERT OR REPLACE so re-running detection on the same date
    overwrites the previous result.

    Args:
        pipe_anomaly_list: output of pipe_detect_engine — list of dicts with
                           keys pipe_name, run_date_id, anomaly_flag.
    """
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    with sqlite3.connect(str(DB_PATH)) as conn:
        for row in pipe_anomaly_list:
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO m_pipe_anomaly_roll_percentile
                        (pipe_name, date_id, anomaly_flag, quantile_10, quantile_90, anomaly_ratio, updated_timestamp_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["pipe_name"],
                        row["run_date_id"],
                        int(row["anomaly_flag"]),
                        row["quantile_10"],
                        row["quantile_90"],
                        row["anomaly_ratio"],
                        updated_at,
                    ),
                )
            except Exception:
                logger.error("[%s] FAILED to save row: %s", row.get("run_date_id"), row, exc_info=True)
                raise
        conn.commit()
    logger.info("Saved %d anomaly results to m_pipe_anomaly_roll_percentile.", len(pipe_anomaly_list))


def pipe_traffic_detect(run_date: str) -> None:
    """
    Run rolling percentile detection across all straits for a given date
    and persist the results to m_pipe_anomaly_roll_percentile.

    Args:
        run_date     : detection date in YYYY-MM-DD format.
    """
    # detect anomalies across all straits
    pipe_anomaly_list = pipe_rp_detect_engine(run_date=run_date)

    # persist results
    save_anomaly_results(pipe_anomaly_list)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Run rolling percentile traffic detection")
    parser.add_argument("--run_date", type=str, required=True, help="Detection date (YYYY-MM-DD)")
    args = parser.parse_args()
    run_date = args.run_date

    # trigger detect
    pipe_traffic_detect(run_date)
