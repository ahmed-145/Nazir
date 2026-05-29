import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

import subprocess
import shutil
from security.validate_path import validate_path
from mcp_server.config import PROJECT_ROOT, TEST_COMMAND, MAX_OUTPUT_BYTES


def run_python(script_path: str, args: list[str] = None) -> str:
    """Run a Python script inside PROJECT_ROOT."""
    resolved = validate_path(script_path)
    cmd = [sys.executable, str(resolved)] + (args or [])
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=60,
    )
    output = result.stdout + result.stderr
    if len(output) > MAX_OUTPUT_BYTES:
        output = output[:MAX_OUTPUT_BYTES] + "\n[truncated]"
    return output or f"(exited {result.returncode} with no output)"


def run_tests(path: str = ".") -> str:
    """Run the test suite via pytest."""
    resolved = validate_path(path)
    result = subprocess.run(
        TEST_COMMAND.split() + [str(resolved), "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=120,
    )
    output = result.stdout + result.stderr
    if len(output) > MAX_OUTPUT_BYTES:
        output = output[:MAX_OUTPUT_BYTES] + "\n[truncated]"
    return output or f"(pytest exited {result.returncode} with no output)"


def lint_file(path: str) -> str:
    """Run ruff (or pyflakes fallback) on a Python file."""
    resolved = validate_path(path)
    if not str(resolved).endswith(".py"):
        return "lint_file only supports .py files"

    if shutil.which("ruff"):
        cmd = ["ruff", "check", str(resolved)]
    elif shutil.which("pyflakes"):
        cmd = ["pyflakes", str(resolved)]
    else:
        return "No linter available (install ruff: pip install ruff)"

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=15,
    )
    output = (result.stdout + result.stderr).strip()
    return output or "No lint issues found"
