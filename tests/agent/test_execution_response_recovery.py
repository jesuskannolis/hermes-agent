"""Approved execution must not end on unsupported unavailability or another plan."""
from unittest.mock import MagicMock, patch
import pytest

REFUSAL = "I need to be transparent: I can’t execute those system changes in this response because the execution tools aren’t available right now. No additional changes were made."
PLAN = "I’ve verified the current state. The next change is structural: repair and deploy the recurring hygiene automation. I’m treating that as the approved structural change for this run. The active app cache stays untouched."
TOOLS = [{"type": "function", "function": {"name": "terminal", "description": "Run a command", "parameters": {"type": "object", "properties": {}}}}]

@pytest.fixture
def agent():
    from run_agent import AIAgent
    with patch("model_tools.get_tool_definitions", return_value=TOOLS), patch("model_tools.check_toolset_requirements", return_value={}), patch("agent.process_bootstrap.OpenAI"):
        a = AIAgent(api_key="test-key-1234567890", base_url="https://openrouter.ai/api/v1", quiet_mode=True, skip_context_files=True, skip_memory=True)
    a.client = MagicMock()
    a._cached_system_prompt = "You are helpful."
    a._use_prompt_caching = False
    a.tool_delay = 0
    a.compression_enabled = False
    a.save_trajectories = False
    a._intent_ack_continuation = True
    a.interim_assistant_callback = MagicMock()
    return a

def run(a, prompt, replies):
    from tests.agent.test_run_agent import _mock_response
    a.client.chat.completions.create.side_effect = [_mock_response(content=r, finish_reason="stop") for r in replies]
    with patch.object(a, "_persist_session"), patch.object(a, "_save_trajectory"), patch.object(a, "_cleanup_task_resources"):
        return a.run_conversation(prompt)

@pytest.mark.parametrize("response", [REFUSAL, PLAN])
def test_approved_execution_reprompts_instead_of_accepting_false_blocker_or_plan(agent, response):
    result = run(agent, "Okay, let’s do it all.", [response, "Blocked: I need your approval to restart the active service."])
    assert agent.client.chat.completions.create.call_count == 2
    assert result["final_response"].startswith("Blocked: I need your approval")
    agent.interim_assistant_callback.assert_not_called()

@pytest.mark.parametrize("prompt,response", [
    ("Why can’t you do it?", REFUSAL),
    ("Stop. Do not make changes.", PLAN),
    ("What should we do next?", PLAN),
    ("Okay, let’s do it all.", "Blocked: permission denied by the service; grant access before retrying."),
    ("Okay, let’s do it all.", "Completed the repair. The next step is to deploy optional improvements."),
])
def test_real_stops_and_non_execution_questions_are_not_retried(agent, prompt, response):
    assert run(agent, prompt, [response])["final_response"] == response
    assert agent.client.chat.completions.create.call_count == 1

def test_persistent_false_refusal_is_bounded_and_reported_without_inventing_a_blocker(agent):
    result = run(agent, "Please implement the approved repair.", [REFUSAL] * 3)
    assert agent.client.chat.completions.create.call_count == 3
    assert "not completed" in result["final_response"]
    assert "tools aren’t available" not in result["final_response"]


@pytest.mark.parametrize("prompt", ["Please only plan the repair", "Please explain how to deploy it", "Can you fix this?", "Do not run it; just review the plan"])
def test_ambiguous_or_planning_request_is_not_promoted_to_execution(agent, prompt):
    assert run(agent, prompt, [REFUSAL])["final_response"] == REFUSAL
    assert agent.client.chat.completions.create.call_count == 1


def test_no_execution_tools_does_not_invent_capability(agent):
    agent.tools = []
    agent.valid_tool_names = set()
    assert run(agent, "Please implement the repair.", [REFUSAL])["final_response"] == REFUSAL
    assert agent.client.chat.completions.create.call_count == 1


def test_disabled_recovery_is_respected(agent):
    agent._intent_ack_continuation = False
    assert run(agent, "Please implement the repair.", [REFUSAL])["final_response"] == REFUSAL
    assert agent.client.chat.completions.create.call_count == 1


def test_recovery_can_execute_a_tool_and_finish(agent):
    from tests.agent.test_run_agent import _mock_response, _mock_tool_call
    agent.client.chat.completions.create.side_effect = [
        _mock_response(content=REFUSAL, finish_reason="stop"),
        _mock_response(content="", finish_reason="tool_calls", tool_calls=[_mock_tool_call(name="terminal", arguments='{"command":"printf verified"}', call_id="check")]),
        _mock_response(content="Completed: the check returned verified.", finish_reason="stop"),
    ]
    with patch.object(agent, "_persist_session"), patch.object(agent, "_save_trajectory"), patch.object(agent, "_cleanup_task_resources"), patch("model_tools.handle_function_call", return_value='{"output":"verified","exit_code":0}') as execute:
        result = agent.run_conversation("Please run the approved check.")
    assert result["final_response"] == "Completed: the check returned verified."
    assert agent.client.chat.completions.create.call_count == 3
    assert execute.call_count == 1
    for call in agent.client.chat.completions.create.call_args_list:
        assert all("_execution_recovery_nudge" not in r for r in call.kwargs["messages"])


def test_actual_request_tool_choice_controls_capability():
    from agent.execution_response_guard import request_tool_names
    assert request_tool_names({"tools": TOOLS}) == ("terminal",)
    assert request_tool_names({"tools": TOOLS, "tool_choice": "none"}) == ()
    assert request_tool_names({"tools": TOOLS, "tool_choice": {"type":"function", "function":{"name":"read_file"}}}) == ()
    assert request_tool_names({"tools": [{"type":"function", "name":"execute_code"}]}) == ("execute_code",)


def test_recent_steering_and_tool_denials_override_original_execution_request():
    from agent.execution_response_guard import execution_response_problem
    prompt = "Please implement the repair."
    assert execution_response_problem(prompt, REFUSAL, [{"role":"user", "content":"Stop now."}], ["terminal"]) is None
    current = [{"role":"user", "content":prompt}, {"role":"tool", "content":"Permission denied"}]
    assert execution_response_problem(prompt, REFUSAL, current, ["terminal"]) is None
    historical = [{"role":"tool", "content":"Permission denied"}, {"role":"user", "content":prompt}]
    assert execution_response_problem(prompt, REFUSAL, historical, ["terminal"]) == "unsupported_tool_unavailability"
