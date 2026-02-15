"""
This script is to 1. combine the changepoints detector with deepseek and sisi-ai.
Once we find the changepoints from pipe data, ask deepseek with web search to get weather and news around the pipe.
Finally, feed the text of weather and news into sisi-ai to rephase, summay and tranlate the text into chinese.
"""
from pprint import pprint
import argparse
import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from mcp_conductor.resources.deepseek.rest_api import DeepSeekClient
from mcp_conductor.resources.sisi.APIs.LLM import SISIClient
from mcp_conductor.detector.pipe_detect_engine import pipe_detect_engine
from mcp_conductor.resources.tools import remove_think_tag
from mcp_conductor.templates.questions import WEB_SEARCH_WEATHER_NEWS

logger = logging.getLogger(__name__)

DB_PATH = Path("./data/sisi.sqlite")


def save_to_log(response: dict, payload: str, question_type: str = "weather_news") -> None:
    """Save a DeepSeek API response to log_agent_work_history."""
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
        logger.info(f"Saved log for return_id={return_id}")
    except Exception as e:
        logger.error(f"Failed to save log: {e}")


def analyze_congestion(pipe_name: str, changepoints: pd.DataFrame) -> str:
    if changepoints.shape[0] == 0:
        pprint(f"🟢 {pipe_name} 通航正常")
    # get the last changepoint
    changepoints_result = changepoints.iloc[[-1], :]

    # deepseek client
    ds_client = DeepSeekClient()
    sisi_client = SISIClient()

    # for each changepoints, request deepseek web search to find out the reason.
    detection_records = []
    for _, row in changepoints_result.iterrows():
        # weather, news
        changepoint_date_id = row['date_id']
        pipe_name = row['pipe_name']
        weather_news_question = WEB_SEARCH_WEATHER_NEWS.format(
            date_id = changepoint_date_id,
            pipe_name = pipe_name
        )

        weather_news_response = ds_client.search_and_ask(
            question=weather_news_question
        )
        logger.info(f"weather_news_response: {weather_news_response}")
        save_to_log(weather_news_response, payload=weather_news_question, question_type="weather_news")
        weather_news_text = weather_news_response["choices"][0]["message"]["content"]

        # # rephase and summay by sisi-ai  
        # TODO: comment out this block as SISI API Issue, will enable once SISI API reover.
        summary_text = weather_news_text
        # summary_resp = sisi_client.search_and_ask(question=weather_news_text)
        # logger.info(f"summary_resp: {summary_resp}")
        # summary_text = remove_think_tag(summary_resp["choices"][0]["message"]["content"])
        # remove think tag
        detection_records.append(
            {
                "date_id": changepoint_date_id,
                "pipe_name": pipe_name,
                "detection": summary_text
            }
        )

    return detection_records[-1]["detection"]


def trigger_traffic_detect(run_date: str, pipe_name: str) -> str:
    changepoints_result: dict[str, pd.DataFrame] = pipe_detect_engine(run_date, pipe_name)
    changepoints = changepoints_result[pipe_name]
    detection_text: str = analyze_congestion(pipe_name=pipe_name, changepoints=changepoints)
    return detection_text


def run_app():
    parser = argparse.ArgumentParser(description='process match polygon for events')
    parser.add_argument(f"--run_date", type=str, required=True, help='Process model run date')
    parser.add_argument(f"--pipe", type=str, required=True, help='Process model on specific pipe')
    args = parser.parse_args()

    run_date = args.__getattribute__("run_date")
    pipe_name = args.__getattribute__("pipe")
    changepoints_result: dict[str, pd.DataFrame] = pipe_detect_engine(run_date, pipe_name)
    changepoints = changepoints_result[pipe_name]
    analyze_congestion(pipe_name=pipe_name, changepoints=changepoints)


if __name__ == "__main__":
    run_app()
