"""Profile database ownership follows exactly the profile state.db symlink."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from gateway import run_runtime


class Registry:
    def __init__(self):
        self.entries = {}

    def add(self, home, value, **kwargs):
        self.entries[home] = value

    def replace(self, home, value):
        self.entries[home] = value

    def remove(self, home):
        self.entries.pop(home)


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ["direct", "nested", "external", "wrong_profile", "wrong_file"])
async def test_profile_authority_store_identity(tmp_path, monkeypatch, layout):
    import gateway.run
    import gateway.session_authority
    home = (tmp_path / "profile").resolve()
    home.mkdir()
    expected = home / "state.db"
    if layout in {"nested", "external"}:
        target = (home / "local-db" if layout == "nested" else tmp_path / "offloaded") / "state.db"
        target.parent.mkdir(parents=True)
        target.touch()
        expected.symlink_to(target)
        actual = target
    else:
        expected.touch()
        actual = expected
    if layout == "wrong_profile":
        actual = tmp_path / "other_profile" / "state.db"
        actual.parent.mkdir()
        actual.touch()
    elif layout == "wrong_file":
        actual = home / "unrelated.db"
        actual.touch()
    monkeypatch.setattr(gateway.run, "_profile_runtime_scope", lambda *a, **kw: nullcontext())
    initialize = AsyncMock(return_value=object())
    monkeypatch.setattr(gateway.session_authority, "initialize_session_authority", initialize)
    registry = Registry()
    runner = SimpleNamespace(_session_db=SimpleNamespace(db_path=str(actual)),
                             session_authorities=registry,
                             session_runtime_descriptor={"instance_id": "test"})
    if layout.startswith("wrong"):
        with pytest.raises(RuntimeError, match="does not belong"):
            await run_runtime._build_profile_authority(runner, "test", home, register=True)
        initialize.assert_not_awaited()
        assert not registry.entries
    else:
        result = await run_runtime._build_profile_authority(runner, "test", home, register=True)
        assert registry.entries[home] is result
        initialize.assert_awaited_once()
