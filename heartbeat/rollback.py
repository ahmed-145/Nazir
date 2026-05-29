"""
Git rollback logic for heartbeat recovery.
Stashes partial work before restarting the agent.
"""
import subprocess
import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()


def stash_partial_work(message: str = "heartbeat-recovery") -> bool:
    """
    Git stash any uncommitted changes so they're not lost.
    Returns True if stash created something, False if working tree was clean.
    """
    result = subprocess.run(
        ["git", "stash", "push", "-m", message,
         ""],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=15,
    )
    return "No local changes" not in result.stdout


def get_last_good_commit() -> str:
    """Return the SHA of the last committed state."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=5,
    )
    return result.stdout.strip()


def write_recovery_task(checkpoint_path: Path, task_queue_path: Path) -> None:
    """
    Write a RECOVERY MODE task so the agent knows to read the checkpoint first.
    """
    if checkpoint_path.exists():
        checkpoint_content = checkpoint_path.read_text()
    else:
        checkpoint_content = "No checkpoint found. Read CLAUDE.md and start fresh."

    recovery_task = (
        "RECOVERY MODE — the heartbeat daemon restarted you.\n\n"
        "1. Read memory/last_checkpoint.md for what you were doing.\n"
        "2. Read CLAUDE.md for project context.\n"
        "3. Resume the pending task from the checkpoint.\n\n"
        f"--- Last checkpoint ---\n{checkpoint_content}"
    )
    task_queue_path.write_text(recovery_task)
