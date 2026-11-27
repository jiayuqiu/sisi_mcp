"""
Analyze anomalous strait and port traffic by querying LLM/web search for
weather and geopolitical/news context around the target date.
"""
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import monotonic
from typing import NotRequired, TypedDict

from mcp_conductor.analyzer.logistics import LogisticsAssessment, LogisticsStatus, assess_logistics
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


class AnomalyWindow(TypedDict):
    anomaly_days: int
    scored_days: int


class AnomalyHistory(TypedDict):
    last_7_days: AnomalyWindow
    last_30_days: AnomalyWindow


class _DeepSeekEvidence(TypedDict):
    summary: str
    weather_factor: str
    political_factor: str
    sources: str
    raw_content: str
    reasoning_content: str


class CongestionAnalysis(_DeepSeekEvidence):
    logistics_status: LogisticsStatus
    logistics_assessment: NotRequired[LogisticsAssessment]


@dataclass(frozen=True)
class _AnomalyContext:
    pipe_name: str
    run_date: date
    location_type: str
    direction: str
    ratio_low: float | None
    ratio_high: float | None
    duration_direction: str
    duration_ratio_low: float | None
    duration_ratio_high: float | None
    regime: str
    anomaly_history: AnomalyHistory | None

    @property
    def date_id(self) -> int:
        return int(self.run_date.strftime("%Y%m%d"))

    def format_prompt(self, template: str, **evidence: str) -> str:
        history = "未提供"
        if self.anomaly_history is not None:
            history = json.dumps({
                name: {
                    "anomaly_days": window["anomaly_days"] if window["scored_days"] else None,
                    "scored_days": window["scored_days"],
                }
                for name, window in self.anomaly_history.items()
            })
        return template.format(
            date_id=self.date_id,
            pipe_name=self.pipe_name,
            location_type=self.location_type,
            direction=self.direction,
            ratio_low=self.ratio_low,
            ratio_high=self.ratio_high,
            duration_direction=self.duration_direction,
            duration_ratio_low=self.duration_ratio_low,
            duration_ratio_high=self.duration_ratio_high,
            regime=self.regime,
            anomaly_history=history,
            **evidence,
        )


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
    context: _AnomalyContext,
    summary: str,
    weather_factor: str,
    political_factor: str,
    sources_json: str,
) -> tuple[str, str]:
    prompt = context.format_prompt(
        ENRICH_ANOMALY_FACTORS,
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
    regime: str = "UNKNOWN",
    *,
    anomaly_history: AnomalyHistory | None = None,
) -> CongestionAnalysis:
    """Collect the causes of a traffic anomaly and assess its logistics impact."""
    started_at = monotonic()
    context = _AnomalyContext(
        pipe_name=pipe_name,
        run_date=datetime.strptime(run_date, "%Y-%m-%d").date(),
        location_type=location_type,
        direction=direction,
        ratio_low=ratio_low,
        ratio_high=ratio_high,
        duration_direction=duration_direction,
        duration_ratio_low=duration_ratio_low,
        duration_ratio_high=duration_ratio_high,
        regime=regime,
        anomaly_history=anomaly_history,
    )
    # request deepseek for summarizing data from sqlite, political news and weather.
    evidence = _collect_deepseek_evidence(context)

    # reqeust logsitics llm model for the effect and suggestionss
    status, assessment = assess_logistics(context, evidence, started_at=started_at)
    result: CongestionAnalysis = {**evidence, "logistics_status": status}
    if assessment is not None:
        result["logistics_assessment"] = assessment
    return result


def _collect_deepseek_evidence(context: _AnomalyContext) -> _DeepSeekEvidence:
    # Disable thinking to keep the custom-tool call inside Dify's timeout.
    ds_client = DeepSeekClient(return_thinking=False)

    today = datetime.now(timezone.utc).date()
    template = (
        WEB_SEARCH_WEATHER_NEWS_WITH_EVIDENCE
        if context.run_date > today
        else WEB_SEARCH_WEATHER_NEWS_STRUCTURED
    )
    question = context.format_prompt(template)

    response = ds_client.search_and_ask(question=question)
    logger.info("DeepSeek response: %s", response)

    message = response["choices"][0]["message"]
    content = message.get("content", "")
    reasoning_content = message.get("reasoning_content", "")

    parsed = _extract_json_object(content) or {}

    # Retry once when the first answer has no usable evidence.
    if not _has_valid_sources(parsed):
        retry_question = context.format_prompt(WEB_SEARCH_WEATHER_NEWS_RETRY)
        retry_response = ds_client.search_and_ask(question=retry_question)
        logger.info("DeepSeek retry response: %s", retry_response)
        retry_message = retry_response["choices"][0]["message"]
        retry_content = retry_message.get("content", "")
        retry_parsed = _extract_json_object(retry_content) or {}
        if _has_valid_sources(retry_parsed):
            response = retry_response
            content = retry_content
            reasoning_content = retry_message.get("reasoning_content", "")
            parsed = retry_parsed

    summary = str(parsed.get("summary", "") or content).strip()
    weather_factor = str(parsed.get("weather_factor", "")).strip()
    political_factor = str(parsed.get("political_factor", "")).strip()
    sources = parsed.get("sources") if isinstance(parsed.get("sources"), list) else []

    normalized_prefix = f"{context.date_id}日，"
    summary = re.sub(r"^\s*\d{4}年\d{1,2}月\d{1,2}日，?", normalized_prefix, summary)

    if _needs_expansion(weather_factor, political_factor):
        sources_json = json.dumps(sources, ensure_ascii=False)
        weather_factor, political_factor = _expand_factors(
            ds_client=ds_client,
            context=context,
            summary=summary,
            weather_factor=weather_factor,
            political_factor=political_factor,
            sources_json=sources_json,
        )

    response["choices"][0]["message"]["content"] = summary

    save_to_log(
        response,
        payload=question,
        date_id=context.date_id,
        pipe_name=context.pipe_name,
        question_type="weather_news",
        location_type=context.location_type,
    )
    return {
        "summary": summary,
        "weather_factor": weather_factor,
        "political_factor": political_factor,
        "sources": json.dumps(sources, ensure_ascii=False),
        "raw_content": content,
        "reasoning_content": reasoning_content,
    }
