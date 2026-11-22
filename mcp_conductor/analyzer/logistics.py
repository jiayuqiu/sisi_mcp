"""Optional Ollama assessment of shipping impacts and stakeholder actions."""

import json
import logging
import math
import os
import re
from time import monotonic
from typing import TYPE_CHECKING, Annotated, Literal

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI
from pydantic import ConfigDict, Field, StringConstraints, TypeAdapter
from typing_extensions import TypedDict

from mcp_conductor.templates.questions import ASSESS_LOGISTICS, LOGISTICS_OUTPUT_LANGUAGE

if TYPE_CHECKING:
    from mcp_conductor.analyzer.congestion import _AnomalyContext, _DeepSeekEvidence

logger = logging.getLogger(__name__)

LogisticsStatus = Literal[
    "available", "disabled", "timeout", "unavailable", "invalid_response", "insufficient_evidence"
]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Recommendation(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")

    stakeholder: Literal["ports_and_terminals", "carriers", "shippers_and_forwarders"]
    action: Annotated[Text, Field(description="用简体中文写明应采取的措施")]
    trigger: Annotated[Text, Field(description="用简体中文写明采取措施的触发条件")]


class LogisticsAssessment(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")

    event_type: Annotated[Text, Field(description="用简体中文概括事件类型")]
    confidence: Literal["low", "medium", "high"]
    impact_scope: Literal["local", "regional", "global", "unknown"]
    impact_summary: Annotated[Text, Field(description="用简体中文说明已观察到的情况和可能的航运影响")]
    evidence_limitations: Annotated[Text, Field(description="用简体中文说明证据局限")]
    recommendations: Annotated[list[Recommendation], Field(min_length=1, max_length=3)]


_ASSESSMENT = TypeAdapter(LogisticsAssessment)
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")


def _has_chinese_report(assessment: LogisticsAssessment) -> bool:
    fields = [assessment["event_type"], assessment["impact_summary"], assessment["evidence_limitations"]]
    for recommendation in assessment["recommendations"]:
        fields.extend((recommendation["action"], recommendation["trigger"]))
    for value in fields:
        han_count = len(_HAN.findall(value))
        if han_count < max(1, 2 * len(_LATIN_WORD.findall(value))):
            return False
    return True


def assess_logistics(
    context: "_AnomalyContext", evidence: "_DeepSeekEvidence", *, started_at: float | None = None
) -> tuple[LogisticsStatus, LogisticsAssessment | None]:
    base_url = os.getenv("OLLAMA_BASE_URL", "").strip()
    model = os.getenv("OLLAMA_LOGISTICS_MODEL", "").strip()
    timeout_setting = os.getenv("OLLAMA_TIMEOUT_SECONDS", "").strip()
    if not (base_url and model and timeout_setting):
        return "disabled", None

    try:
        timeout = float(timeout_setting)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("the timeout must be finite and positive")
    except ValueError:
        logger.warning("Invalid OLLAMA_TIMEOUT_SECONDS configuration")
        return "disabled", None

    history = context.anomaly_history
    if history is not None and history["last_30_days"]["scored_days"] == 0:
        has_sources = any(
            isinstance(source, dict)
            and str(source.get("url", "")).strip().startswith(("http://", "https://"))
            for source in json.loads(evidence["sources"])
        )
        if not has_sources:
            return "insufficient_evidence", None

    if started_at is not None:
        try:
            tool_timeout = float(os.getenv("API_TOOL_DEFAULT_READ_TIMEOUT", "60"))
            if not math.isfinite(tool_timeout) or tool_timeout <= 0:
                raise ValueError("the tool timeout must be finite and positive")
        except ValueError:
            logger.warning("Invalid API_TOOL_DEFAULT_READ_TIMEOUT configuration")
            return "disabled", None
        # Leave time for the API to serialize the response and Dify to receive it.
        remaining = started_at + tool_timeout - monotonic() - 5
        if remaining <= 0:
            logger.info("Skipping Ollama because the Dify tool deadline is near")
            return "timeout", None
        timeout = min(timeout, remaining)

    prompt = context.format_prompt(
        ASSESS_LOGISTICS,
        summary=evidence["summary"],
        weather_factor=evidence["weather_factor"],
        political_factor=evidence["political_factor"],
        sources_json=evidence["sources"],
    )
    messages = [
        {"role": "system", "content": LOGISTICS_OUTPUT_LANGUAGE},
        {"role": "user", "content": prompt},
    ]
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "logistics_assessment", "schema": _ASSESSMENT.json_schema()},
    }
    deadline = monotonic() + timeout
    try:
        with OpenAI(base_url=base_url, api_key="dummy", timeout=timeout, max_retries=0) as client:
            for attempt in range(2):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return "timeout", None
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1024,
                    stream=False,
                    timeout=remaining,
                    response_format=response_format,
                )
                choice = response.choices[0]
                if choice.finish_reason != "stop":
                    raise ValueError("Ollama did not finish the assessment")
                content = choice.message.content
                assessment = _ASSESSMENT.validate_json(content, strict=True)
                if _has_chinese_report(assessment):
                    return "available", assessment
                if attempt == 0:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": (
                            "上次回复包含英文正文。请将事件类型、影响说明、证据局限、各项行动及触发条件改写为简体中文。"
                            "保留原有事实、置信度和 JSON 结构，只返回完整的 JSON 对象。"
                        )},
                    ]
    except APITimeoutError:
        logger.warning("Ollama logistics request timed out")
        return "timeout", None
    except APIConnectionError:
        logger.warning("Could not connect to Ollama for logistics assessment")
        return "unavailable", None
    except APIError as exc:
        logger.warning("Ollama logistics request failed (%s)", type(exc).__name__)
        return "unavailable", None

    except (AttributeError, IndexError, TypeError, ValueError):
        logger.warning("Ollama returned an invalid logistics assessment")
        return "invalid_response", None

    logger.warning("Ollama logistics assessment did not use Chinese after a rewrite")
    return "invalid_response", None
