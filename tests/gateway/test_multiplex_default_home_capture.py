"""Regression tests for a multiplex primary bot capturing a secondary profile home.

The primary-handler factories run during the same startup pass that wires secondary
profiles.  They must never freeze the context-local ``get_hermes_home()`` value present
at construction time; each event must start from the gateway process home.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway.config import GatewayConfig, Platform


def _runner(tmp_path, monkeypatch):
    from gateway.run import GatewayRunner

    process_home = tmp_path / "hermes-root"
    process_home.mkdir()
    (process_home / "config.yaml").write_text("{}\n", encoding="utf-8")
    secondary_home = tmp_path / "profiles" / "athena"
    secondary_home.mkdir(parents=True)
    (secondary_home / "config.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(process_home))

    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(multiplex_profiles=True)
    return runner, process_home, secondary_home


def _construct_under_secondary(secondary_home, factory):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(str(secondary_home))
    try:
        return factory()
    finally:
        reset_hermes_home_override(token)


@pytest.mark.asyncio
async def test_primary_message_resolves_process_home_per_event(tmp_path, monkeypatch):
    from hermes_constants import get_hermes_home

    runner, process_home, secondary_home = _runner(tmp_path, monkeypatch)
    runner._admit_primary_source = lambda _source, default_home: default_home  # type: ignore[method-assign]

    async def _handle_message(_event):
        return Path(get_hermes_home())

    runner._handle_message = _handle_message  # type: ignore[method-assign]
    handler = _construct_under_secondary(secondary_home, runner._primary_message_handler)

    result = await handler(SimpleNamespace(source=SimpleNamespace(profile=None)))
    assert result == process_home


@pytest.mark.asyncio
async def test_primary_busy_handler_resolves_process_home_per_event(tmp_path, monkeypatch):
    from hermes_constants import get_hermes_home

    runner, process_home, secondary_home = _runner(tmp_path, monkeypatch)
    runner._admit_primary_source = lambda _source, default_home: default_home  # type: ignore[method-assign]
    runner._session_key_for_source = lambda _source: "primary-session"  # type: ignore[method-assign]

    async def _handle_busy(_event, _session_key):
        return Path(get_hermes_home())

    runner._handle_active_session_busy_message = _handle_busy  # type: ignore[method-assign]
    handler = _construct_under_secondary(secondary_home, runner._primary_busy_session_handler)

    result = await handler(SimpleNamespace(source=SimpleNamespace(profile=None)), "ignored")
    assert result == process_home


@pytest.mark.asyncio
async def test_primary_platform_event_resolves_process_home_per_event(tmp_path, monkeypatch):
    from hermes_constants import get_hermes_home

    runner, process_home, secondary_home = _runner(tmp_path, monkeypatch)
    runner._admit_primary_source = lambda _source, default_home: default_home  # type: ignore[method-assign]

    async def _handle_platform_event(_event, _source):
        return Path(get_hermes_home())

    runner._handle_gateway_platform_event = _handle_platform_event  # type: ignore[method-assign]
    handler = _construct_under_secondary(secondary_home, runner._primary_platform_event_handler)

    result = await handler({}, SimpleNamespace(profile=None))
    assert result == process_home


def test_primary_auth_check_resolves_process_home_per_call(tmp_path, monkeypatch):
    runner, process_home, secondary_home = _runner(tmp_path, monkeypatch)
    runner.adapters = {}
    seen = []

    def _canonicalize(_source, *, primary_home=None, **_kwargs):
        seen.append(primary_home)
        return SimpleNamespace(runtime_home=primary_home)

    runner._canonicalize = _canonicalize  # type: ignore[method-assign]
    runner._is_user_authorized_for_source = lambda _source: True  # type: ignore[method-assign]
    check = _construct_under_secondary(
        secondary_home,
        lambda: runner._make_adapter_auth_check(Platform.TELEGRAM),
    )

    assert check("jj", chat_type="dm", chat_id="8669747148") is True  # type: ignore[call-arg]
    assert seen == [process_home]
