"""
Nazir heartbeat daemon — Phase 4.

Monitors /tmp/nazir-heartbeat. If it goes stale for >5 minutes:
  1. Stash partial work (git stash)
  2. Write RECOVERY MODE task to current_task.md
  3. Restart claude-agent.service via systemctl --user
  4. After 3 consecutive failures → notify + pause

Run as: systemctl --user start heartbeat.service
Or directly: python3 heartbeat/daemon.py
"""
import time
import subprocess
import os
import sys
from pathlib import Path

# Bootstrap project root
PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from heartbeat.notify import notify
from heartbeat.rollback import stash_partial_work, write_recovery_task

HEARTBEAT_FILE = Path("/tmp/nazir-heartbeat")
CHECKPOINT_FILE = PROJECT_ROOT / "memory" / "last_checkpoint.md"
TASK_FILE = PROJECT_ROOT / "memory" / "current_task.md"
LOG_FILE = PROJECT_ROOT / "logs" / "heartbeat.log"

TIMEOUT_SECONDS = 300   # 5 minutes — stale heartbeat = agent is stuck
CHECK_INTERVAL = 60     # check every minute
MAX_FAILURES = 3        # strikes before pausing


def log(msg: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def heartbeat_age() -> float:
    """Seconds since the heartbeat file was last touched. 9999 if missing."""
    if not HEARTBEAT_FILE.exists():
        return 9999.0
    return time.time() - HEARTBEAT_FILE.stat().st_mtime


def restart_agent() -> bool:
    """Restart the claude-agent user service. Returns True on success."""
    result = subprocess.run(
        ["systemctl", "--user", "restart", "claude-agent.service"],
        capture_output=True, text=True, timeout=15,
    )
    return result.returncode == 0


def pause_agent() -> None:
    """Write PAUSE marker so task-loop wrapper stops polling."""
    TASK_FILE.write_text("PAUSE")
    log("Agent paused. Set memory/current_task.md to resume.")


def run() -> None:
    log(f"Heartbeat daemon started. Watching {HEARTBEAT_FILE}")
    log(f"Timeout: {TIMEOUT_SECONDS}s | Max failures: {MAX_FAILURES}")
    notify("Nazir Started", "Heartbeat daemon is running.", urgency="low")

    failures = 0

    while True:
        time.sleep(CHECK_INTERVAL)

        age = heartbeat_age()

        if age <= TIMEOUT_SECONDS:
            if failures > 0:
                log(f"Heartbeat recovered (age={age:.0f}s). Resetting failure count.")
                failures = 0
            continue

        # Heartbeat stale — but don't restart if there's nothing to do
        task_content = TASK_FILE.read_text().strip() if TASK_FILE.exists() else ""
        idle_states = {"DONE", "IDLE", "PAUSE"}
        if any(task_content.upper().startswith(s) for s in idle_states):
            log(f"Stale heartbeat ({age:.0f}s) but task is idle ({task_content[:40]!r}). Skipping restart.")
            continue

        failures += 1
        log(f"Stale heartbeat ({age:.0f}s old). Failure {failures}/{MAX_FAILURES}.")

        if failures >= MAX_FAILURES:
            log("Max failures reached. Pausing agent and notifying.")
            notify(
                "Nazir Needs Attention",
                f"Agent failed to recover {MAX_FAILURES} times. "
                "Check logs/heartbeat.log. Set current_task.md to resume.",
                urgency="critical",
            )
            pause_agent()
            # Reset failures so daemon keeps running (watchdog mode)
            failures = 0
            continue

        log(f"Recovery attempt {failures}/{MAX_FAILURES}...")

        # 1. Stash partial work
        stashed = stash_partial_work(f"heartbeat-recovery-{failures}")
        if stashed:
            log("Stashed uncommitted changes.")

        # 2. Write recovery task
        write_recovery_task(CHECKPOINT_FILE, TASK_FILE)
        log("Wrote RECOVERY MODE task.")

        # 3. Restart agent
        if restart_agent():
            log("claude-agent.service restarted.")
            notify(
                "Nazir Recovery",
                f"Agent restarted (attempt {failures}/{MAX_FAILURES}).",
                urgency="normal",
            )
        else:
            log("WARNING: systemctl --user restart failed. Is claude-agent.service enabled?")
            notify("Nazir Warning", "Failed to restart claude-agent.service.", urgency="critical")


if __name__ == "__main__":
    run()
