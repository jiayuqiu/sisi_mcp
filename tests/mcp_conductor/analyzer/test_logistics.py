import json
from dataclasses import replace
from datetime import date
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openai import APIConnectionError, APITimeoutError

from mcp_conductor.analyzer.congestion import _AnomalyContext
from mcp_conductor.analyzer.logistics import assess_logistics


@pytest.fixture
def inputs():
    context = _AnomalyContext(
        pipe_name="金斯顿港",
        run_date=date(2026, 10, 12),
        location_type="port",
        direction="NORMAL",
        ratio_low=0,
        ratio_high=0,
        duration_direction="HIGH",
        duration_ratio_low=0,
        duration_ratio_high=0.5,
        regime="DELAY",
        anomaly_history={
            "last_7_days": {"anomaly_days": 6, "scored_days": 7},
            "last_30_days": {"anomaly_days": 8, "scored_days": 25},
        },
    )
    evidence = {
        "summary": "港口靠泊时间偏长。",
        "weather_factor": "天气数据有限。",
        "political_factor": "暂缺可核实公告。",
        "sources": "[]",
        "raw_content": "raw DeepSeek response",
        "reasoning_content": "internal reasoning",
    }
    return context, evidence


@pytest.fixture
def ollama_client(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.example/v1")
    monkeypatch.setenv("OLLAMA_LOGISTICS_MODEL", "qwen3-14b-pretrain-f16:latest")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "12.5")
    with patch("mcp_conductor.analyzer.logistics.OpenAI") as client:
        yield client, client.return_value.__enter__.return_value.chat.completions.create


@pytest.fixture
def chinese_assessment():
    return {
        "event_type": "局部靠泊延误",
        "confidence": "low",
        "impact_scope": "local",
        "impact_summary": "靠泊等待可能影响该港的集疏运。",
        "evidence_limitations": "缺少港口通告，需核实延误原因。",
        "recommendations": [
            {"stakeholder": "ports_and_terminals", "action": "通过 AIS 核实泊位排期", "trigger": "到港排队持续"},
        ],
    }


def _completion(assessment):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content=json.dumps(assessment)),
    )])


def test_logistics_uses_validated_chinese_assessment(inputs, ollama_client, chinese_assessment):
    client, create = ollama_client
    create.return_value = _completion(chinese_assessment)

    assert assess_logistics(*inputs) == ("available", chinese_assessment)
    client.assert_called_once_with(
        base_url="http://ollama.example/v1", api_key="dummy", timeout=12.5, max_retries=0,
    )
    settings = create.call_args.kwargs
    assert settings["model"] == "qwen3-14b-pretrain-f16:latest"
    assert settings["response_format"]["type"] == "json_schema"
    assert "简体中文" in settings["messages"][0]["content"]
    prompt = settings["messages"][1]["content"]
    assert '"scored_days": 25' in prompt
    assert "港口靠泊时间偏长。" in prompt
    assert "internal reasoning" not in prompt


def test_logistics_rewrites_english_with_the_remaining_budget(inputs, ollama_client, chinese_assessment):
    _, create = ollama_client
    english = {**chinese_assessment, "event_type": "low_traffic_without_clear_cause"}
    create.side_effect = [_completion(english), _completion(chinese_assessment)]

    assert assess_logistics(*inputs) == ("available", chinese_assessment)
    first, rewrite = (call.kwargs for call in create.call_args_list)
    assert 0 < rewrite["timeout"] < first["timeout"] <= 12.5
    assert "改写为简体中文" in rewrite["messages"][-1]["content"]


def test_logistics_rejects_english_advice_even_with_chinese_intro(inputs, ollama_client, chinese_assessment):
    _, create = ollama_client
    chinese_assessment["recommendations"][0]["trigger"] = "条件：monitor for consecutive days of very low traffic"
    create.return_value = _completion(chinese_assessment)

    assert assess_logistics(*inputs) == ("invalid_response", None)
    assert create.call_count == 2


def test_logistics_skips_unconfigured_client(inputs, ollama_client, monkeypatch):
    client, _ = ollama_client
    monkeypatch.delenv("OLLAMA_BASE_URL")
    assert assess_logistics(*inputs) == ("disabled", None)
    client.assert_not_called()


def test_logistics_skips_request_when_deepseek_used_dify_time_budget(inputs, ollama_client, monkeypatch):
    client, _ = ollama_client
    monkeypatch.setenv("API_TOOL_DEFAULT_READ_TIMEOUT", "180")
    assert assess_logistics(*inputs, started_at=monotonic() - 176) == ("timeout", None)
    client.assert_not_called()


def test_logistics_skips_when_history_and_sources_are_unavailable(inputs, ollama_client):
    client, _ = ollama_client
    context, evidence = inputs
    context = replace(context, anomaly_history={
        "last_7_days": {"anomaly_days": 0, "scored_days": 0},
        "last_30_days": {"anomaly_days": 0, "scored_days": 0},
    })
    assert assess_logistics(context, evidence) == ("insufficient_evidence", None)
    assert '"anomaly_days": null' in context.format_prompt("{anomaly_history}")
    client.assert_not_called()


@pytest.mark.parametrize("content", [None, "invalid JSON", '{"impact_scope":"regional"}'])
def test_logistics_invalid_output_falls_back(inputs, ollama_client, content):
    _, create = ollama_client
    create.return_value.choices = [SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content=content),
    )]
    assert assess_logistics(*inputs) == ("invalid_response", None)


@pytest.mark.parametrize(
    ("error", "status"),
    [(APITimeoutError, "timeout"), (APIConnectionError, "unavailable")],
)
def test_logistics_request_error_falls_back(inputs, ollama_client, error, status):
    _, create = ollama_client
    create.side_effect = error(request=None)
    assert assess_logistics(*inputs) == (status, None)
