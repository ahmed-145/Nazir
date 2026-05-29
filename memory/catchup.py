#!/usr/bin/env python3
"""
Nazir context restore — Phase 5.

Reads memory/last_checkpoint.md and restores Gemini session UUIDs
into gemini_runner.ACTIVE_SESSIONS.

Called:
  - By Claude Code SessionStart hook (at the start of every session)
  - Directly by the agent via the `catchup` MCP tool
  - Manually: python3 memory/catchup.py

Returns the checkpoint text so the agent can read context immediately.
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

CHECKPOINT_FILE = PROJECT_ROOT / "memory" / "last_checkpoint.md"
SESSIONS_FILE   = PROJECT_ROOT / "memory" / "gemini_sessions.json"
TASK_FILE       = PROJECT_ROOT / "memory" / "current_task.md"


def restore() -> str:
    """
    Restore context from last checkpoint.
    - Loads Gemini session UUIDs into gemini_runner.ACTIVE_SESSIONS
    - Returns the checkpoint text for the agent to read

    Returns:
        Formatted context string for the agent.
    """
    lines = []

    # 1. Read checkpoint
    if CHECKPOINT_FILE.exists():
        checkpoint = CHECKPOINT_FILE.read_text().strip()
        lines.append(checkpoint)
    else:
        lines.append("# No previous checkpoint found. Starting fresh.")
        lines.append("Read CLAUDE.md for project context.")

    # 2. Restore Gemini sessions
    sessions_restored = 0
    if SESSIONS_FILE.exists():
        try:
            sessions = json.loads(SESSIONS_FILE.read_text())
            if sessions:
                try:
                    from orchestrator.gemini_runner import ACTIVE_SESSIONS, load_sessions
                    load_sessions(SESSIONS_FILE)
                    sessions_restored = len(sessions)
                    lines.append(
                        f"\n## Sessions Restored\n"
                        + "\n".join(f"- {k}: {v[:8]}..." for k, v in sessions.items())
                    )
                except ImportError:
                    lines.append(f"\n## Sessions (not loaded — gemini_runner unavailable)")
        except json.JSONDecodeError:
            lines.append("\n## Sessions: gemini_sessions.json is corrupt")

    # 3. Add current task
    if TASK_FILE.exists():
        task = TASK_FILE.read_text().strip()
        if task and task not in ("DONE", "PAUSE", ""):
            lines.append(f"\n## Current Task\n{task}")

    return "\n".join(lines)


def summary() -> dict:
    """Return a structured summary of checkpoint state for MCP tool response."""
    has_checkpoint = CHECKPOINT_FILE.exists()
    has_sessions   = SESSIONS_FILE.exists()

    sessions = {}
    if has_sessions:
        try:
            sessions = json.loads(SESSIONS_FILE.read_text())
        except json.JSONDecodeError:
            pass

    task = ""
    if TASK_FILE.exists():
        task = TASK_FILE.read_text().strip()

    checkpoint_age = None
    if has_checkpoint:
        import time
        checkpoint_age = int(time.time() - CHECKPOINT_FILE.stat().st_mtime)

    return {
        "has_checkpoint": has_checkpoint,
        "checkpoint_age_seconds": checkpoint_age,
        "sessions_count": len(sessions),
        "sessions": list(sessions.keys()),
        "current_task": task[:100] if task else None,
    }


if __name__ == "__main__":
    # Called from SessionStart hook: python3 memory/catchup.py
    context = restore()
    print(context)
    s = summary()
    print(f"\n[Nazir catchup] Restored {s['sessions_count']} session(s). "
          f"Checkpoint age: {s['checkpoint_age_seconds']}s")
