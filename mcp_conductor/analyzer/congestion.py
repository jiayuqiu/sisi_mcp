"""
Analyze anomalous strait and port traffic by querying LLM/web search for
weather and geopolitical/news context around the target date.
"""
import json
import re
from datetime import datetime, timezone

from mcp_conductor.resources.deepseek.rest_api import DeepSeekClient
from mcp_conductor.resources.utils.db import save_to_log
from mcp_conductor.resources.utils.logger import get_logger
from mcp_conductor.templates.questions import (
    ENRICH_ANOMALY_FACTORS,
    WEB_SEARCH_WEATHER_NEWS_RETRY,
    WEB_SEARCH_WEATHER_NEWS_STRUCTURED,
    WEB_SEARCH_WEATHER_NEWS_WITH_EVIDENCE,
)

logger = get_logger(__name__)


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
    location_type: str = "pipe",
    direction: str = "UNKNOWN",
    ratio_low: float | None = None,
    ratio_high: float | None = None,
    duration_direction: str = "UNKNOWN",
    duration_ratio_low: float | None = None,
    duration_ratio_high: float | None = None,
    llm_client: str | None = None,  # TODO: deepseek, add local llm into here.
    regime: str = "UNKNOWN",
) -> dict[str, str]:
    """Query DeepSeek for weather/news context on the anomaly date."""
    run_date_id = int(run_date.replace("-", ""))
    # The reports need concise evidence, not a long reasoning trace. Disabling
    # thinking keeps the custom-tool call comfortably inside Dify's timeout.
    ds_client = DeepSeekClient(return_thinking=False)  # TODO: deepseek, add local llm into here.

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

    save_to_log(
        response,
        payload=question,
        date_id=run_date_id,
        pipe_name=pipe_name,
        question_type="weather_news",
        location_type=location_type,
    )
    return {
        "summary": summary,
        "weather_factor": weather_factor,
        "political_factor": political_factor,
        "sources": json.dumps(sources, ensure_ascii=False),
        "raw_content": content,
        "reasoning_content": reasoning_content,
    }
