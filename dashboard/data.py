"""
Nazir Dashboard — data layer.

Pure functions — no UI dependency. All reads are safe (never raise on missing files).
Consumed by Textual widgets and by export.py.
"""
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()

HEARTBEAT_FILE  = Path("/tmp/nazir-heartbeat")
SESSIONS_FILE   = PROJECT_ROOT / "memory" / "gemini_sessions.json"
TASK_LOG        = PROJECT_ROOT / "memory" / "task_log.jsonl"
CURRENT_TASK    = PROJECT_ROOT / "memory" / "current_task.md"
CHECKPOINT_FILE = PROJECT_ROOT / "memory" / "last_checkpoint.md"


# ── Heartbeat ─────────────────────────────────────────────────────────────────

def heartbeat_age() -> Optional[int]:
    """Seconds since /tmp/nazir-heartbeat was last touched. None if file missing."""
    if not HEARTBEAT_FILE.exists():
        return None
    return int(time.time() - HEARTBEAT_FILE.stat().st_mtime)


def heartbeat_label() -> str:
    """Human-readable heartbeat age: '12s ago', 'STALE (4m)', 'missing'."""
    age = heartbeat_age()
    if age is None:
        return "missing"
    if age < 60:
        return f"{age}s ago"
    minutes = age // 60
    if age > 300:
        return f"STALE ({minutes}m)"
    return f"{minutes}m ago"


def heartbeat_ok() -> bool:
    """True if heartbeat is fresh (< 5 min)."""
    age = heartbeat_age()
    return age is not None and age < 300


# ── systemd services ──────────────────────────────────────────────────────────

def service_status(name: str) -> str:
    """'active' | 'inactive' | 'failed' | 'unknown'"""
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", name],
            capture_output=True, text=True, timeout=3
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def agent_status() -> str:
    return service_status("claude-agent.service")


def heartbeat_service_status() -> str:
    return service_status("heartbeat.service")


# ── Gemini sessions ───────────────────────────────────────────────────────────

def active_sessions() -> dict[str, str]:
    """Load active Gemini session UUIDs from disk."""
    if not SESSIONS_FILE.exists():
        return {}
    try:
        return json.loads(SESSIONS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def session_count() -> int:
    return len(active_sessions())


# ── Current task ──────────────────────────────────────────────────────────────

def current_task_text() -> str:
    """Text from memory/current_task.md. Empty string if file missing or DONE."""
    if not CURRENT_TASK.exists():
        return ""
    text = CURRENT_TASK.read_text().strip()
    if text in ("DONE", "PAUSE", ""):
        return ""
    return text


def is_agent_busy() -> bool:
    """True when current_task.md has a real (non-DONE) task."""
    return bool(current_task_text())


# ── Task history ──────────────────────────────────────────────────────────────

def recent_tasks(n: int = 8) -> list[dict]:
    """
    Last n entries from task_log.jsonl, newest first.
    Each dict: {timestamp, status, task, result}
    """
    if not TASK_LOG.exists():
        return []
    try:
        lines = TASK_LOG.read_text().strip().splitlines()
        entries = []
        for line in reversed(lines):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries) >= n:
                break
        return entries
    except OSError:
        return []


def _age_label(ts_str: str) -> str:
    """'2m ago', '3h ago', 'just now'"""
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = int(time.time() - ts.timestamp())
        if age < 60:
            return "just now"
        if age < 3600:
            return f"{age // 60}m ago"
        if age < 86400:
            return f"{age // 3600}h ago"
        return f"{age // 86400}d ago"
    except Exception:
        return "?"


def recent_tasks_formatted(n: int = 8) -> list[dict]:
    """Like recent_tasks() but adds an 'age' field."""
    tasks = recent_tasks(n)
    for t in tasks:
        t["age"] = _age_label(t.get("timestamp", ""))
    return tasks


# ── Metrics / cost ────────────────────────────────────────────────────────────

def cost_summary() -> dict:
    """
    Returns dict with week + lifetime savings. Safe — returns zeros on error.
    Keys: week_delegations, week_dollars, lifetime_delegations, lifetime_dollars,
          lifetime_gemini_tokens, lifetime_claude_avoided, top_tasks
    """
    try:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        from orchestrator.metrics import cost_report
        week = cost_report("week")
        all_ = cost_report("all")
        return {
            "week_delegations":       week["delegations"],
            "week_dollars":           week["dollars_saved"],
            "lifetime_delegations":   all_["delegations"],
            "lifetime_dollars":       all_["dollars_saved"],
            "lifetime_gemini_tokens": all_["gemini_tokens"],
            "lifetime_claude_avoided":all_["claude_tokens_avoided"],
            "avg_latency_ms":         all_["avg_latency_ms"],
            "top_tasks":              all_["top_tasks"],
        }
    except Exception:
        return {
            "week_delegations": 0, "week_dollars": 0.0,
            "lifetime_delegations": 0, "lifetime_dollars": 0.0,
            "lifetime_gemini_tokens": 0, "lifetime_claude_avoided": 0,
            "avg_latency_ms": 0, "top_tasks": [],
        }


def delegation_ratio() -> tuple[int, int, float]:
    """
    (claude_avoided_tokens, gemini_tokens, ratio_pct)
    ratio_pct = gemini / (claude + gemini) * 100
    """
    s = cost_summary()
    gemini = s["lifetime_gemini_tokens"]
    avoided = s["lifetime_claude_avoided"]
    total = gemini + avoided
    ratio = (gemini / total * 100) if total > 0 else 0.0
    return avoided, gemini, ratio


# ── Snapshot (for export) ─────────────────────────────────────────────────────

def full_snapshot() -> dict:
    """All dashboard data in one dict. Used by export.py."""
    costs = cost_summary()
    return {
        "generated_at":       datetime.now().isoformat(),
        "heartbeat_label":    heartbeat_label(),
        "heartbeat_ok":       heartbeat_ok(),
        "agent_status":       agent_status(),
        "heartbeat_svc":      heartbeat_service_status(),
        "session_count":      session_count(),
        "sessions":           active_sessions(),
        "current_task":       current_task_text(),
        "is_busy":            is_agent_busy(),
        "recent_tasks":       recent_tasks_formatted(10),
        "costs":              costs,
    }
