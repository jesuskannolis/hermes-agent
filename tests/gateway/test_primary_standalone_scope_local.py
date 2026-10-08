from pathlib import Path
from types import SimpleNamespace
import pytest
from gateway.config import GatewayConfig

@pytest.mark.asyncio
@pytest.mark.parametrize('boundary',['message','busy','platform'])
async def test_standalone_primary_does_not_inherit_another_profile(tmp_path, monkeypatch, boundary):
 from gateway.run import GatewayRunner
 from hermes_constants import get_hermes_home,set_hermes_home_override,reset_hermes_home_override
 from agent.secret_scope import set_multiplex_active
 home=tmp_path/'primary';other=tmp_path/'athena';home.mkdir();other.mkdir()
 (home/'config.yaml').write_text('terminal:\n  cwd: '+str(home)+'\n')
 (home/'.env').write_text('')
 monkeypatch.setenv('HERMES_HOME',str(home));set_multiplex_active(False)
 runner=GatewayRunner.__new__(GatewayRunner);runner.config=GatewayConfig(multiplex_profiles=False)
 async def handler(*args):return Path(get_hermes_home())
 runner._handle_message=handler;runner._handle_active_session_busy_message=handler;runner._handle_gateway_platform_event=handler
 token=set_hermes_home_override(str(other))
 try:
  if boundary=='message':result=await runner._primary_message_handler()(SimpleNamespace(source=SimpleNamespace(profile=None)))
  elif boundary=='busy':result=await runner._primary_busy_session_handler()(SimpleNamespace(source=SimpleNamespace(profile=None)),'session')
  else:result=await runner._primary_platform_event_handler()({},SimpleNamespace(profile=None))
  assert result==home
  assert get_hermes_home()==other  # outer scope is restored, not globally mutated
 finally:reset_hermes_home_override(token)
