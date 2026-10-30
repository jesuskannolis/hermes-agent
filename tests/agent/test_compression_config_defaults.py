"""A failed config load hands ``_parse_compression_config`` ``{}``; every key must fall back to
DEFAULT_CONFIG, and an explicit ``threshold_tokens: null`` must stay the ratio-only opt-out."""

from types import SimpleNamespace

import pytest

from agent.agent_init import _parse_compression_config
from hermes_cli.config import DEFAULT_CONFIG


def _agent():
    return SimpleNamespace(model="m", provider="openrouter", api_mode="chat_completions", quiet_mode=True)


@pytest.mark.parametrize(
    ("agent_cfg", "expected"),
    [
        ({}, DEFAULT_CONFIG["compression"]["threshold_tokens"]),  # config-load failure → shipped default
        ({"compression": {"threshold_tokens": None}}, None),  # explicit null → ratio-only opt-out
    ],
)
def test_threshold_tokens_default_and_null_opt_out(agent_cfg, expected):
    cs = _parse_compression_config(_agent(), agent_cfg)
    assert cs.threshold_tokens == expected
    assert cs.threshold == DEFAULT_CONFIG["compression"]["threshold"]


def test_explicit_codex_cap_survives_small_context_floor():
    from unittest.mock import patch
    from agent.context_compressor import ContextCompressor
    agent = SimpleNamespace(model="gpt-5.6-sol", provider="openai-codex", api_mode="codex_responses", quiet_mode=True)
    cs = _parse_compression_config(agent, {"compression": {
        "threshold": 0.4, "codex_gpt55_autoraise": False, "threshold_tokens": 108800,
    }})
    with patch("agent.context_compressor.get_model_context_length", return_value=272000):
        compressor = ContextCompressor(model=agent.model, threshold_percent=cs.threshold, threshold_tokens_cap=cs.threshold_tokens, quiet_mode=True)
        assert compressor.context_length == 272000
        assert compressor.threshold_tokens == 108800
    assert agent._compression_threshold_autoraised is None
