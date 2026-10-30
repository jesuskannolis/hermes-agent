"""Bounded recovery for explicit execution requests; never grants tool permission."""
from __future__ import annotations
import re

_EXECUTION_TOOLS = {"terminal", "execute_code", "write_file", "patch", "file_write", "edit_file"}
_EXECUTE = re.compile(r"\b(?:let['’]s do (?:it|this|that|them|all)|go ahead|take action|(?:please |can you |could you )?(?:implement|repair|fix|execute|build|deploy|run|create|update)\b)", re.IGNORECASE)
_QUESTION_OR_STOP = re.compile(r"^(?:please\s+)?(?:why\b|how\b|what\b|explain\b|describe\b|review\b|should\b|stop\b|cancel\b|hold\b|wait\b|don['’]t\b|do not\b)", re.IGNORECASE)
_PLAN_ONLY_REQUEST = re.compile(r"\b(?:only|just) (?:plan|explain|describe|review)|\b(?:do not|don['’]t) (?:execute|act|implement|run|deploy|make changes)|\bshow me how\b", re.IGNORECASE)
_UNAVAILABLE = re.compile(r"\b(?:execution |terminal |coding )?tools?\s+(?:are(?:n['’]t| not)|is(?:n['’]t| not))\s+available\b|\b(?:no access to|don['’]t have access to)\s+(?:the )?(?:execution |terminal )tools\b", re.IGNORECASE)
_PLAN = re.compile(r"\b(?:the )?next (?:step|change|action)\s+is\b[^.!?\n]{0,180}\b(?:repair|fix|implement|deploy|run|build|create|update|execute)\b", re.IGNORECASE)
_DONE_OR_ACTIVE = re.compile(r"(?:^|[.!?\n]\s*)(?:i(?:['’]ve| have)?\s+)?(?:completed|finished|deployed|implemented|fixed|resolved)\b|\b(?:worker|job|process) (?:is |still )?(?:running|queued)\b", re.IGNORECASE)
_BLOCKER = re.compile(r"\b(?:permission denied|access denied|approval required|need your approval|waiting for (?:your|client|human) approval|quota exceeded|rate limit|missing credentials)\b", re.IGNORECASE)

NUDGE = (
    "Execution check: the current request includes execution tools, but your response ended with "
    "an unsupported capability claim or another plan for the approved work. Check the actual "
    "tool result and current task state. Take the next safe, authorized step now, or name the "
    "specific verified blocker or required human decision. Do not repeat a completed mutation, "
    "bypass permissions, restart an active service without approval, or infer a root cause."
)
EXHAUSTED = (
    "The requested work is not completed. The execution check retried twice, but I still ended "
    "without carrying it through. I have not verified a tool outage or another concrete blocker. "
    "Retained work needs inspection before any retry."
)

def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(p.get("text", "") for p in value if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""

def request_tool_names(kwargs):
    """Names from the actual post-middleware payload, excluding schemas and arguments."""
    choice = kwargs.get("tool_choice")
    if choice == "none" or (isinstance(choice, dict) and choice.get("type") == "none"):
        return ()
    names = []
    for tool in kwargs.get("tools") or []:
        if isinstance(tool, dict):
            name = (tool.get("function") or tool).get("name")
            if isinstance(name, str):
                names.append(name)
    if isinstance(choice, dict):
        selected = (choice.get("function") or choice).get("name")
        if selected:
            names = [n for n in names if n == selected]
    return tuple(sorted(set(names)))

def execution_response_problem(user_message, response, messages, offered_tools):
    """A retry hint, not a declaration that the model or runtime is broken."""
    if not _EXECUTION_TOOLS.intersection(offered_tools):
        return None
    latest = next((r.get("content") for r in reversed(messages) if r.get("role") == "user" and not r.get("_execution_recovery_nudge")), user_message)
    user = text_content(latest).strip().strip('"“”').strip()
    user = re.sub(r"^(?:(?:okay|ok|yes|alright|well)[,!. ]+)+", "", user, flags=re.IGNORECASE)
    if _QUESTION_OR_STOP.search(user) or _PLAN_ONLY_REQUEST.search(user) or "?" in user or not _EXECUTE.search(user):
        return None
    text = text_content(response).replace("**", "")
    if _DONE_OR_ACTIVE.search(text) or _BLOCKER.search(text):
        return None
    # Only current-turn tool failures count; old history cannot disable recovery forever.
    for row in reversed(messages):
        if row.get("role") == "user" and not row.get("_execution_recovery_nudge"):
            break
        if row.get("role") == "tool" and _BLOCKER.search(text_content(row.get("content"))):
            return None
    if _UNAVAILABLE.search(text):
        return "unsupported_tool_unavailability"
    if _PLAN.search(text):
        return "execution_plan_without_completion"
    return None
