"""Choose a bounded text-response recovery without changing permission or history."""

from agent.agent_runtime_helpers import (
    intent_ack_continuation_mode, looks_like_degenerate_final,
    promoted_reasoning_announces_action, trailing_continue_intent,
)
from agent.execution_response_guard import execution_response_problem


def choose_continuation(agent, user_message, response, text, messages, retries, promoted, tool_rows):
    mode = intent_ack_continuation_mode(agent)
    if bool(getattr(agent, "_stall_guards", True)) and mode != "off":
        problem = execution_response_problem(
            user_message, text, messages, getattr(agent, "_last_request_tool_names", ()),
        )
        if problem:
            return ("exhausted" if retries >= 2 else "execution"), problem
    return _legacy_continuation(agent, mode, user_message, response, text, messages, retries, promoted, tool_rows), None


def _legacy_continuation(agent, mode, user_message, response, text, messages, retries, promoted, tool_rows):
    # All recovery types share the existing two-nudge budget. Announced actions
    # outrank fragment recovery, and acknowledgement detection remains last.
    if retries >= 2:
        return None
    guards = bool(getattr(agent, "_stall_guards", True))
    if guards and agent.valid_tool_names and (
        trailing_continue_intent(text)
        or (bool(promoted) and promoted_reasoning_announces_action(text))
    ):
        return "stall"
    if guards and mode != "off" and tool_rows > 0 and looks_like_degenerate_final(text, user_message=user_message):
        return "degenerate"
    if mode != "off" and agent.valid_tool_names and agent._looks_like_codex_intermediate_ack(
        user_message=user_message, assistant_content=response, messages=messages,
        require_workspace=(mode == "codex_only"),
    ):
        return "ack"
    return None
