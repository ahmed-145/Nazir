"""
Task queue — reads current_task.md and manages the task loop.
Used by the systemd task-loop wrapper (run-claude.sh) and the heartbeat daemon.
"""
import json
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
CURRENT_TASK_FILE = MEMORY_DIR / "current_task.md"
TASK_LOG_FILE = MEMORY_DIR / "task_log.jsonl"
COMPLETED_MARKER = "DONE"
PAUSE_MARKER = "PAUSE"


def read_current_task() -> str:
    """Return the current task text, or empty string if none."""
    if CURRENT_TASK_FILE.exists():
        return CURRENT_TASK_FILE.read_text().strip()
    return ""


def write_task(task: str) -> None:
    """Set a new task."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_TASK_FILE.write_text(task)


def mark_done(task: str, result: str = "") -> None:
    """Log completed task and clear current_task.md."""
    _append_log({
        "timestamp": datetime.now().isoformat(),
        "status": "completed",
        "task": task[:200],
        "result": result[:500],
    })
    CURRENT_TASK_FILE.write_text(COMPLETED_MARKER)


def mark_failed(task: str, error: str = "") -> None:
    """Log failed task."""
    _append_log({
        "timestamp": datetime.now().isoformat(),
        "status": "failed",
        "task": task[:200],
        "error": error[:500],
    })


def is_paused() -> bool:
    return read_current_task() == PAUSE_MARKER


def is_done() -> bool:
    return read_current_task() == COMPLETED_MARKER


def has_task() -> bool:
    task = read_current_task()
    return bool(task) and task not in (COMPLETED_MARKER, PAUSE_MARKER)


def wait_for_task(poll_interval: int = 5, timeout: int = 3600) -> str:
    """
    Block until a task appears in current_task.md.
    Returns the task text. Used by the task-loop wrapper.
    """
    start = time.time()
    while time.time() - start < timeout:
        if is_paused():
            time.sleep(30)
            continue
        task = read_current_task()
        if task and not is_done():
            return task
        time.sleep(poll_interval)
    return ""


def _append_log(entry: dict) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASK_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def tail_log(n: int = 10) -> list[dict]:
    """Return last n entries from task log."""
    if not TASK_LOG_FILE.exists():
        return []
    lines = TASK_LOG_FILE.read_text().strip().splitlines()
    return [json.loads(l) for l in lines[-n:] if l.strip()]
