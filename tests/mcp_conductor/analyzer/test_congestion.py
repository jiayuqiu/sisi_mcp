import json
from unittest.mock import MagicMock, patch

from mcp_conductor.analyzer import analyze_congestion
from mcp_conductor.analyzer.congestion import (
    _extract_json_object,
    _has_valid_sources,
    _needs_expansion,
)


def test_extract_json_object_handles_fenced_and_inline_json():
    fenced = '```json\n{"summary": "ok"}\n```'
    assert _extract_json_object(fenced) == {"summary": "ok"}

    inline = 'Note before {"summary": "inline"} note after'
    assert _extract_json_object(inline) == {"summary": "inline"}

    assert _extract_json_object("") is None
    assert _extract_json_object("not json") is None


def test_has_valid_sources_requires_two_http_urls():
    assert not _has_valid_sources({})
    assert not _has_valid_sources({"sources": [{"url": "https://a.example"}]})
    assert _has_valid_sources(
        {
            "sources": [
                {"url": "https://a.example"},
                {"url": "http://b.example"},
            ]
        }
    )


def test_needs_expansion_flags_short_or_weak_factors():
    long_weather = "海面季风增强导致局部海域阵风达到八级以上，能见度明显下降并对大型集装箱船航速造成一定延误。" * 2
    long_political = (
        "红海周边地缘安全摩擦持续升温，多艘商船被迫调整航速与值守措施，局部航道通行不确定性显著抬升。" * 2
    )
    assert not _needs_expansion(long_weather, long_political)
    assert _needs_expansion("未检索到显著天气风险信号。", long_political)
    assert _needs_expansion("简短天气描述", long_political)


def test_analyze_congestion_retries_on_missing_sources_and_logs_result():
    first_payload = {
        "summary": "2026年4月16日，霍尔木兹海峡受阻。",
        "weather_factor": "简短天气。",
        "political_factor": "简短政治。",
        "sources": [{"url": "https://only-one.example"}],
    }
    retry_payload = {
        "summary": "2026年4月16日，霍尔木兹海峡通航受阻风险上升。",
        "weather_factor": "短天气。",
        "political_factor": "短政治。",
        "sources": [
            {"title": "s1", "url": "https://one.example"},
            {"title": "s2", "url": "https://two.example"},
        ],
    }
    expanded_payload = {
        "weather_factor": "扩展后的天气因素详述。",
        "political_factor": "扩展后的政治因素详述。",
    }

    mock_client = MagicMock()
    mock_client.search_and_ask.side_effect = [
        {"choices": [{"message": {"content": json.dumps(first_payload, ensure_ascii=False)}}]},
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(retry_payload, ensure_ascii=False),
                        "reasoning_content": "retry reasoning",
                    }
                }
            ]
        },
    ]
    mock_client.chat.return_value = {
        "choices": [{"message": {"content": json.dumps(expanded_payload, ensure_ascii=False)}}]
    }

    with (
        patch("mcp_conductor.analyzer.congestion.DeepSeekClient", return_value=mock_client),
        patch("mcp_conductor.analyzer.congestion.save_to_log") as mock_save_log,
    ):
        result = analyze_congestion(
            "霍尔木兹海峡",
            "2026-04-16",
            location_type="pipe",
            direction="LOW",
            ratio_low=0.6,
            ratio_high=0.1,
            duration_direction="HIGH",
            duration_ratio_low=0.0,
            duration_ratio_high=0.5,
            regime="BLOCKAGE",
        )

    assert mock_client.search_and_ask.call_count == 2
    assert mock_client.chat.call_count == 1
    assert result["summary"] == "20260416日，霍尔木兹海峡通航受阻风险上升。"
    assert result["weather_factor"] == "扩展后的天气因素详述。"
    assert result["political_factor"] == "扩展后的政治因素详述。"
    assert result["reasoning_content"] == "retry reasoning"
    mock_save_log.assert_called_once()
