"""
Gemini CLI subprocess manager.

Verified facts from probe_phase0_5.py (2026-05-29, gemini-cli v0.41.2):
- JSON output keys: session_id, response, stats  (issue #14435 RESOLVED)
- --resume <uuid> works in headless mode — session memory confirmed
- Auth env var for daemon: GEMINI_API_KEY (not GOOGLE_API_KEY)
- Exit code 41 = auth failure (JSON body also contains error.code=41)
- --yolo takes ~8s to initialise — use timeout >= 60s
- stderr contains IDE extension warnings — safe to ignore
"""
import subprocess
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()

ACTIVE_SESSIONS: dict[str, str] = {}  # task_name → session_uuid


def _gemini_env() -> dict:
    """Environment for all Gemini CLI subprocesses."""
    env = dict(os.environ)
    # GEMINI_API_KEY is the correct var for forcing API key auth in daemon mode.
    # Falls back to GOOGLE_API_KEY if GEMINI_API_KEY not set.
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    env["GEMINI_API_KEY"] = key
    env["GEMINI_TELEMETRY_ENABLED"] = "false"
    env["GEMINI_TELEMETRY_TARGET"] = "local"
    return env


def run_gemini(
    prompt: str,
    task_name: str = None,
    new_session: bool = False,
    timeout: int = 180,
) -> str:
    """
    Run a prompt via Gemini CLI headless mode.

    Args:
        prompt:       The prompt to send.
        task_name:    Key for session tracking. If set, resumes existing session.
        new_session:  Force a new session even if one exists for task_name.
        timeout:      Seconds. --yolo takes ~8s to init — keep >= 60.

    Returns:
        The model's response text.

    Raises:
        RuntimeError: On auth failure (exit 41) or any other non-zero exit.
    """
    # --allowed-mcp-server-names none: disables all MCP servers in subprocess
    # Cuts cold-start from ~58s to ~10s (MCP servers don't need to load for analysis/codegen)
    cmd = ["gemini", "--yolo", "--output-format", "json",
           "--allowed-mcp-server-names", "none"]

    if task_name and task_name in ACTIVE_SESSIONS and not new_session:
        cmd += ["--resume", ACTIVE_SESSIONS[task_name]]

    cmd += ["-p", prompt]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.DEVNULL,  # prevents "no stdin" warning
        env=_gemini_env(),
    )

    # Parse JSON first — error bodies also come as JSON (e.g. exit 41)
    data = {}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pass

    if result.returncode == 41 or (data.get("error", {}).get("code") == 41):
        raise RuntimeError(
            f"Gemini auth failed (exit 41). "
            f"Set GEMINI_API_KEY in .env. "
            f"Error: {data.get('error', {}).get('message', result.stderr[:200])}"
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"Gemini exit {result.returncode}: "
            f"{data.get('error', {}).get('message', result.stderr[:300])}"
        )

    # Store session UUID for future --resume calls
    # session_id is present in every successful JSON response (v0.41.2+)
    session_id = data.get("session_id")
    if session_id and task_name:
        ACTIVE_SESSIONS[task_name] = session_id

    # Record metrics (Phase 6) — fire-and-forget, never block on failure
    try:
        from orchestrator.metrics import record
        record(
            stats=data.get("stats", {}),
            task_name=task_name,
            prompt=prompt[:120] if prompt else None,
            session_id=session_id,
        )
    except Exception:
        pass  # metrics are never load-bearing

    return data.get("response", result.stdout)


def save_sessions(path: Path) -> None:
    """Persist active session UUIDs to disk (call in every /wrapup)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ACTIVE_SESSIONS, indent=2))


def load_sessions(path: Path) -> None:
    """Restore session UUIDs from disk (call on session start / catchup)."""
    if path.exists():
        ACTIVE_SESSIONS.update(json.loads(path.read_text()))


def check_quota() -> dict:
    """
    Returns the stats block from a minimal Gemini call.
    Reuses an existing session to avoid slow CLAUDE.md context reload.
    Returns empty dict on timeout (quota unknown — treat as ok).
    """
    # Reuse any existing session to skip the ~8s CLAUDE.md load
    cmd = ["gemini", "--yolo", "--output-format", "json",
           "--allowed-mcp-server-names", "none"]
    if ACTIVE_SESSIONS:
        latest_uuid = next(iter(ACTIVE_SESSIONS.values()))
        cmd += ["--resume", latest_uuid]
    cmd += ["-p", "hi"]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=60, stdin=subprocess.DEVNULL, env=_gemini_env(),
        )
        data = json.loads(result.stdout)
        return data.get("stats", {})
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return {}  # quota unknown — caller treats as ok
