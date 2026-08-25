"""Unit tests for AI Assistant and LLM Analyst endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from dao_vang.web.ai_analyst import (
    ask_ai_analyst,
    build_context_summary,
    build_system_prompt,
)


def test_build_system_prompt():
    prompt = build_system_prompt("BTCUSDT", "sample context")
    assert "PeakPulse" in prompt or "ĐẢO VÀNG" in prompt or "BTCUSDT" in prompt


def test_build_context_summary():
    context = {
        "current_price": 105.5,
        "signal_price": 108.0,
        "probability": 84.5,
        "risk_level": "HIGH",
        "btc_regime": "FOMO",
        "parabolic_pump": True,
        "metrics": {
            "oi_change_24h": "+18.2%",
            "funding_rate": "+0.0450%",
            "taker_buy_ratio": "42.0%",
        },
        "trade_setup": {
            "entry_price": 108.0,
            "invalidation_price": 112.5,
            "tp1_price": 103.68,
            "tp2_price": 99.36,
            "risk_reward_ratio": "1.92",
        },
        "shap_drivers": [
            {"feature_name": "Volume Exhaustion", "impact_percentage": 34.5},
            {"feature_name": "Funding Climax", "impact_percentage": 28.0},
        ],
    }
    summary = build_context_summary("SOLUSDT", context)
    assert "SOLUSDT" in summary
    assert "$105.5" in summary
    assert "84.5%" in summary
    assert "HIGH" in summary
    assert "+18.2%" in summary
    assert "$112.5" in summary


def test_ask_ai_analyst_rule_based_fallback():
    context = {
        "current_price": 50.0,
        "signal_price": 52.0,
        "probability": 78.0,
        "risk_level": "HIGH",
        "metrics": {"oi_change_24h": "+12.0%", "funding_rate": "+0.035%"},
        "trade_setup": {"invalidation_price": 54.0, "tp1_price": 49.92, "tp2_price": 47.84},
    }

    # Test why score is high with disabled LLM or no API key
    with patch("dao_vang.config.settings.AppSettings.ai", create=True) as mock_ai:
        mock_ai.api_key = None
        mock_ai.enabled = True
        res1 = ask_ai_analyst("Tại sao con này có điểm cao?", "LINKUSDT", context, llm_config={"enabled": False})
        assert res1["provider"] == "Built-in Quantitative Engine"
        assert "LINKUSDT" in res1["answer"]
        assert "78.0%" in res1["answer"] or "Phân Tích Nguyên Nhân" in res1["answer"]

        # Test SL/TP question
        res2 = ask_ai_analyst("Điểm cắt lỗ an toàn ở đâu?", "LINKUSDT", context, llm_config={"enabled": False})
        assert "$54.0" in res2["answer"] or "Cắt Lỗ" in res2["answer"]

        # Test BTC scenario question
        res3 = ask_ai_analyst("Kịch bản nếu BTC tăng?", "LINKUSDT", context, llm_config={"enabled": False})
        assert "BTC" in res3["answer"] or "Bitcoin" in res3["answer"]


def test_ask_ai_analyst_gemini_mock():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "candidates": [
            {"content": {"parts": [{"text": "Gemini response for DOGEUSDT"}]}}
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = ask_ai_analyst(
            "Phân tích coin này giúp tôi",
            "DOGEUSDT",
            {"current_price": 0.25, "probability": 85.0},
            llm_config={
                "provider": "gemini",
                "apiKey": "dummy-key",
                "modelId": "gemini-1.5-flash",
                "enabled": True,
            },
        )
        assert res["provider"] == "Google Gemini"
        assert res["answer"] == "Gemini response for DOGEUSDT"


def test_ask_ai_analyst_server_default_mock():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "choices": [
            {"message": {"content": "Server AI proxy response for SOLUSDT"}}
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = ask_ai_analyst(
            "Phân tích SOLUSDT",
            "SOLUSDT",
            {"current_price": 140.0, "probability": 80.0},
            llm_config={},  # Empty config from client
        )
        assert "Gemini 3.7 Flash Tiered (Proxy)" in res["provider"] or "OpenAI" in res["provider"]
        assert res["answer"] == "Server AI proxy response for SOLUSDT"
