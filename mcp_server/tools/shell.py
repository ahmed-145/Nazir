import subprocess
import sys
import os
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

from security.validate_path import validate_path
from security.blocklist import check_command
from mcp_server.config import PROJECT_ROOT, MAX_OUTPUT_BYTES


def safe_run_command(cmd: str, cwd: str = None, timeout: int = 30, dry_run: bool = False) -> str:
    """
    Run a shell command inside PROJECT_ROOT with blocklist + path checks.
    Returns combined stdout+stderr, truncated to MAX_OUTPUT_BYTES.
    """
    check_command(cmd)
    if dry_run:
        return f"DRY_RUN: would execute: {cmd}"

    resolved_cwd = str(validate_path(cwd)) if cwd else str(PROJECT_ROOT)

    result = subprocess.run(
        cmd, shell=True,
        capture_output=True, text=True,
        cwd=resolved_cwd,
        timeout=timeout,
        env={**os.environ, "NAZIR_PROJECT_ROOT": str(PROJECT_ROOT)},
    )
    output = result.stdout + result.stderr
    if len(output) > MAX_OUTPUT_BYTES:
        output = output[:MAX_OUTPUT_BYTES] + f"\n[truncated — {len(output)} bytes total]"
    return output


def ping_heartbeat() -> str:
    """Touch the heartbeat file. Daemon kills agent if this goes stale >5 min."""
    import pathlib
    pathlib.Path("/tmp/nazir-heartbeat").touch()
    return "heartbeat ok"
