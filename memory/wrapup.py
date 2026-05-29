#!/usr/bin/env python3
"""
Nazir context checkpoint writer — Phase 5.

Writes memory/last_checkpoint.md and archives to memory/checkpoints/.
Also persists active Gemini session UUIDs.

Called:
  - By Claude Code PreCompact hook (before context is compacted)
  - By Claude Code Stop hook (when agent exits)
  - Directly by the agent via the `wrapup` MCP tool
  - Manually: python3 memory/wrapup.py

Usage as MCP tool:
    wrapup(task, completed, pending, decisions, files_modified, blockers)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

CHECKPOINT_FILE = PROJECT_ROOT / "memory" / "last_checkpoint.md"
CHECKPOINTS_DIR = PROJECT_ROOT / "memory" / "checkpoints"
SESSIONS_FILE   = PROJECT_ROOT / "memory" / "gemini_sessions.json"


def write_checkpoint(
    task: str,
    completed: list[str] = None,
    pending: list[str] = None,
    decisions: list[str] = None,
    files_modified: list[str] = None,
    blockers: list[str] = None,
    gemini_sessions: dict = None,
) -> str:
    """
    Write a context checkpoint to memory/last_checkpoint.md and archive it.
    Returns the path to the archived checkpoint.
    """
    completed      = completed      or []
    pending        = pending        or []
    decisions      = decisions      or []
    files_modified = files_modified or []
    blockers       = blockers       or []

    # Grab live Gemini sessions if not provided
    if gemini_sessions is None:
        if SESSIONS_FILE.exists():
            try:
                gemini_sessions = json.loads(SESSIONS_FILE.read_text())
            except json.JSONDecodeError:
                gemini_sessions = {}
        else:
            gemini_sessions = {}

    ts = datetime.now().isoformat()

    def bullet(items): return "\n".join(f"- {i}" for i in items) or "(none)"

    sessions_block = "\n".join(
        f"- {k}: {v}" for k, v in gemini_sessions.items()
    ) or "(none)"

    content = f"""# Nazir Context Checkpoint
Generated: {ts}

## Current Task
{task}

## Completed Steps
{bullet(completed)}

## Pending (resume here)
{bullet(pending)}

## Key Decisions Made
{bullet(decisions)}

## Files Modified This Session
{bullet(files_modified)}

## Blockers / Issues
{bullet(blockers)}

## Active Gemini CLI Sessions
{sessions_block}
"""

    # Write current checkpoint
    CHECKPOINT_FILE.write_text(content)

    # Archive it
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".md"
    archive_path = CHECKPOINTS_DIR / archive_name
    archive_path.write_text(content)

    # Persist Gemini sessions separately (for fast load by gemini_runner)
    if gemini_sessions:
        SESSIONS_FILE.write_text(json.dumps(gemini_sessions, indent=2))

    return str(archive_path)


def quick_wrapup(task: str = "") -> str:
    """
    Minimal checkpoint with just the task string — for hook-triggered saves
    where we don't have structured data. Reads task from current_task.md if empty.
    """
    if not task:
        task_file = PROJECT_ROOT / "memory" / "current_task.md"
        task = task_file.read_text().strip() if task_file.exists() else "Unknown task"

    # Try to load existing checkpoint to preserve completed/pending if possible
    existing = {}
    if CHECKPOINT_FILE.exists():
        existing_text = CHECKPOINT_FILE.read_text()
        # Extract pending section if it exists
        if "## Pending (resume here)" in existing_text:
            sections = existing_text.split("## ")
            for s in sections:
                if s.startswith("Pending"):
                    lines = [l.lstrip("- ").strip() for l in s.splitlines()[1:] if l.strip().startswith("-")]
                    existing["pending"] = lines
                    break

    return write_checkpoint(
        task=task,
        pending=existing.get("pending", ["(context saved mid-session — check CLAUDE.md and git log)"]),
        decisions=["(auto-saved by PreCompact/Stop hook)"],
    )


if __name__ == "__main__":
    # Called from hook: python3 memory/wrapup.py
    result = quick_wrapup()
    print(f"[Nazir wrapup] Checkpoint saved: {result}")
