"""Operator-owned Changeover execution standby; live-read for every entry point."""
import json
from pathlib import Path

MESSAGE = 'Native Kanban execution is paused. Use the existing ClickUp task and the approved direct handoff; no Kanban work was queued.'

def paused():
    marker = Path.home() / '.changeover/state/agent-execution-standby.json'
    if not marker.exists():
        return False
    try:
        return json.loads(marker.read_text(encoding="utf-8-sig")).get('kanban') == 'paused'
    except (OSError, ValueError, TypeError):
        return True  # broken control state never silently enables dispatch

def assert_available():
    if paused():
        raise PermissionError(MESSAGE)
