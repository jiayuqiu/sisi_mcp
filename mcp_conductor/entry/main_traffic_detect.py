"""
Detect anomalous strait traffic using the rolling percentile method.
When an anomaly is found, query DeepSeek (web search) for weather and news
context around that date, then return the summary.

TODO: not a entry script, will move to a better place later.
"""
import argparse
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mcp_conductor.resources.utils.db import get_engine
from mcp_conductor.resources.utils.logger import get_logger
from mcp_conductor.detector.detect_engine import rp_detect_engine
from mcp_conductor.detector.roll_percentile.monitor import monitor_roll_percentile
from mcp_conductor.resources.deepseek.rest_api import DeepSeekClient
from mcp_conductor.templates.questions import (
    ENRICH_ANOMALY_FACTORS,
    WEB_SEARCH_WEATHER_NEWS_RETRY,
    WEB_SEARCH_WEATHER_NEWS_STRUCTURED,
    WEB_SEARCH_WEATHER_NEWS_WITH_EVIDENCE,
)
from mcp_conductor.resources.utils.db import save_to_log


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


def _extract_json_object(text: str) -> dict[str, str] | None:
    """Extract the first JSON object from a model response."""
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _has_valid_sources(data: dict[str, object]) -> bool:
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        return False
    valid = 0
    for item in sources:
        if isinstance(item, dict):
            url = str(item.get("url", "")).strip()
            if url.startswith("http://") or url.startswith("https://"):
                valid += 1
    return valid >= 2


def _needs_expansion(weather_factor: str, political_factor: str) -> bool:
    weak_markers = ["未检索到显著", "无显著", "风险较低"]
    text = f"{weather_factor}\n{political_factor}"
    if any(m in text for m in weak_markers):
        return True
    if len(weather_factor.strip()) < 40 or len(political_factor.strip()) < 50:
        return True
    return False


def _expand_factors(
    ds_client: DeepSeekClient,
    run_date_id: int,
    pipe_name: str,
    direction: str,
    ratio_low: float | None,
    ratio_high: float | None,
    duration_direction: str,
    duration_ratio_low: float | None,
    duration_ratio_high: float | None,
    regime: str,
    summary: str,
    weather_factor: str,
    political_factor: str,
    sources_json: str,
) -> tuple[str, str]:
    prompt = ENRICH_ANOMALY_FACTORS.format(
        date_id=run_date_id,
        pipe_name=pipe_name,
        direction=direction,
        ratio_low=ratio_low,
        ratio_high=ratio_high,
        duration_direction=duration_direction,
        duration_ratio_low=duration_ratio_low,
        duration_ratio_high=duration_ratio_high,
        regime=regime,
        summary=summary,
        weather_factor=weather_factor or "",
        political_factor=political_factor or "",
        sources_json=sources_json,
    )
    response = ds_client.chat(
        messages=[{"role": "user", "content": prompt}],
        model="deepseek-chat",
        web_search=False,
        temperature=0.2,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _extract_json_object(content) or {}
    w = str(parsed.get("weather_factor", "")).strip() or weather_factor
    p = str(parsed.get("political_factor", "")).strip() or political_factor
    return w, p


def analyze_congestion(
    pipe_name: str,
    run_date: str,
    direction: str = "UNKNOWN",
    ratio_low: float | None = None,
    ratio_high: float | None = None,
    duration_direction: str = "UNKNOWN",
    duration_ratio_low: float | None = None,
    duration_ratio_high: float | None = None,
    regime: str = "UNKNOWN",
) -> dict[str, str]:
    """Query DeepSeek for weather/news context on the anomaly date."""
    run_date_id = int(run_date.replace("-", ""))
    # The reports need concise evidence, not a long reasoning trace. Disabling
    # thinking keeps the custom-tool call comfortably inside Dify's timeout.
    ds_client = DeepSeekClient(return_thinking=False)

    run_date_obj = datetime.strptime(run_date, "%Y-%m-%d").date()
    today = datetime.now(timezone.utc).date()
    if run_date_obj > today:
        question = WEB_SEARCH_WEATHER_NEWS_WITH_EVIDENCE.format(
            date_id=run_date_id,
            pipe_name=pipe_name,
            direction=direction,
            ratio_low=ratio_low,
            ratio_high=ratio_high,
            duration_direction=duration_direction,
            duration_ratio_low=duration_ratio_low,
            duration_ratio_high=duration_ratio_high,
            regime=regime,
        )
    else:
        question = WEB_SEARCH_WEATHER_NEWS_STRUCTURED.format(
            date_id=run_date_id,
            pipe_name=pipe_name,
            direction=direction,
            ratio_low=ratio_low,
            ratio_high=ratio_high,
            duration_direction=duration_direction,
            duration_ratio_low=duration_ratio_low,
            duration_ratio_high=duration_ratio_high,
            regime=regime,
        )

    response = ds_client.search_and_ask(question=question)
    logger.info("DeepSeek response: %s", response)

    message = response["choices"][0]["message"]
    content = message.get("content", "")
    reasoning_content = message.get("reasoning_content", "")

    parsed = _extract_json_object(content) or {}

    # Retry once when the first answer has no usable evidence.
    if not _has_valid_sources(parsed):
        retry_question = WEB_SEARCH_WEATHER_NEWS_RETRY.format(
            date_id=run_date_id,
            pipe_name=pipe_name,
            direction=direction,
            ratio_low=ratio_low,
            ratio_high=ratio_high,
            duration_direction=duration_direction,
            duration_ratio_low=duration_ratio_low,
            duration_ratio_high=duration_ratio_high,
            regime=regime,
        )
        retry_response = ds_client.search_and_ask(question=retry_question)
        logger.info("DeepSeek retry response: %s", retry_response)
        retry_message = retry_response["choices"][0]["message"]
        retry_content = retry_message.get("content", "")
        retry_parsed = _extract_json_object(retry_content) or {}
        if _has_valid_sources(retry_parsed):
            response = retry_response
            message = retry_message
            content = retry_content
            reasoning_content = retry_message.get("reasoning_content", "")
            parsed = retry_parsed

    summary = str(parsed.get("summary", "") or content).strip()
    weather_factor = str(parsed.get("weather_factor", "")).strip()
    political_factor = str(parsed.get("political_factor", "")).strip()
    sources = parsed.get("sources") if isinstance(parsed.get("sources"), list) else []

    normalized_prefix = f"{run_date_id}日，"
    summary = re.sub(r"^\s*\d{4}年\d{1,2}月\d{1,2}日，?", normalized_prefix, summary)

    if _needs_expansion(weather_factor, political_factor):
        sources_json = json.dumps(sources, ensure_ascii=False)
        weather_factor, political_factor = _expand_factors(
            ds_client=ds_client,
            run_date_id=run_date_id,
            pipe_name=pipe_name,
            direction=direction,
            ratio_low=ratio_low,
            ratio_high=ratio_high,
            duration_direction=duration_direction,
            duration_ratio_low=duration_ratio_low,
            duration_ratio_high=duration_ratio_high,
            regime=regime,
            summary=summary,
            weather_factor=weather_factor,
            political_factor=political_factor,
            sources_json=sources_json,
        )

    response["choices"][0]["message"]["content"] = summary

    save_to_log(response, payload=question, date_id=run_date_id, pipe_name=pipe_name, question_type="weather_news")
    return {
        "summary": summary,
        "weather_factor": weather_factor,
        "political_factor": political_factor,
        "sources": json.dumps(sources, ensure_ascii=False),
        "raw_content": content,
        "reasoning_content": reasoning_content,
    }


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
    # TODO: add check app_anomaly_list before save the results to sqlite
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
    parser.add_argument("--run_date", type=str, required=True, help="Detection date (YYYY-MM-DD)")
    args = parser.parse_args()
    run_date = args.run_date

    # trigger detect
    traffic_detect(run_date)
