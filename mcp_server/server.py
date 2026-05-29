"""
Nazir custom MCP server — Phase 2.

Tools exposed to Claude Code and Gemini CLI:
  Shell:   safe_run_command, ping_heartbeat
  Files:   safe_read_file, safe_write_file, list_dir
  Git:     git_status, git_diff, git_log, git_commit, git_add, git_stash, git_stash_pop
  Search:  search_in_files, find_files
  Code:    run_python, run_tests, lint_file

All file/path operations are validated against NAZIR_PROJECT_ROOT.
All shell commands are checked against the blocklist.

Run:
    python3 mcp_server/server.py

Register with Claude Code:
    claude mcp add nazir-tools -- python3 /path/to/mcp_server/server.py

Register with Gemini CLI:
    Added to ~/.gemini/settings.json mcpServers automatically by Phase 2 setup.
"""
import sys
from pathlib import Path

# Ensure project root is on path for security/ imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP
from mcp_server.tools.shell import safe_run_command, ping_heartbeat
from mcp_server.tools.files import safe_read_file, safe_write_file, list_dir
from mcp_server.tools.git import (
    git_status, git_diff, git_log,
    git_commit, git_add, git_stash, git_stash_pop,
)
from mcp_server.tools.search import search_in_files, find_files
from mcp_server.tools.code import run_python, run_tests, lint_file

mcp = FastMCP("nazir-tools")


# ── Shell ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def run_command(cmd: str, cwd: str = None, timeout: int = 30) -> str:
    """
    Run a shell command inside PROJECT_ROOT.
    Blocked: rm -rf, mkfs, sudo, fork bombs, and other destructive patterns.
    cwd must be inside PROJECT_ROOT if provided.
    """
    return safe_run_command(cmd, cwd, timeout)


@mcp.tool()
def heartbeat() -> str:
    """
    Touch /tmp/nazir-heartbeat. Call after every subtask.
    The heartbeat daemon restarts the agent if this goes stale for >5 minutes.
    """
    return ping_heartbeat()


# ── Files ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def read_file(path: str) -> str:
    """Read a file. Path must be inside PROJECT_ROOT."""
    return safe_read_file(path)


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """
    Write content to a file. Path must be inside PROJECT_ROOT.
    Creates parent directories automatically.
    """
    return safe_write_file(path, content)


@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List directory contents (hidden files excluded). Path must be inside PROJECT_ROOT."""
    return list_dir(path)


# ── Git ────────────────────────────────────────────────────────────────────────

@mcp.tool()
def status() -> str:
    """Show git status (short format with branch)."""
    return git_status()


@mcp.tool()
def diff(staged: bool = False) -> str:
    """
    Show git diff. Set staged=True for staged (pre-commit) diff.
    Output truncated at 20KB.
    """
    return git_diff(staged)


@mcp.tool()
def log(n: int = 10) -> str:
    """Show last n git commits (one-line format)."""
    return git_log(n)


@mcp.tool()
def commit(message: str) -> str:
    """
    Stage all tracked modifications (git add -u) and commit.
    For untracked files, call stage() first.
    """
    return git_commit(message)


@mcp.tool()
def stage(paths: list[str]) -> str:
    """Stage specific files for the next commit (git add)."""
    return git_add(paths)


@mcp.tool()
def stash(message: str = "") -> str:
    """Stash current working directory changes."""
    return git_stash(message)


@mcp.tool()
def stash_pop() -> str:
    """Pop the most recent git stash."""
    return git_stash_pop()


# ── Search ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def search(pattern: str, path: str = ".", file_glob: str = None) -> str:
    """
    Search for a regex pattern in files using ripgrep.
    file_glob: e.g. "*.py" to restrict to Python files.
    Returns file:line:match format.
    """
    return search_in_files(pattern, path, file_glob)


@mcp.tool()
def find(pattern: str, path: str = ".") -> str:
    """
    Find files by name pattern (e.g. "*.py", "test_*").
    Returns paths relative to PROJECT_ROOT.
    """
    return find_files(pattern, path)


# ── Code ───────────────────────────────────────────────────────────────────────

@mcp.tool()
def run_script(script_path: str, args: list[str] = None) -> str:
    """Run a Python script inside PROJECT_ROOT. Returns stdout+stderr."""
    return run_python(script_path, args)


@mcp.tool()
def test(path: str = ".") -> str:
    """
    Run the test suite via pytest.
    path: directory or file to test (default: entire project).
    """
    return run_tests(path)


@mcp.tool()
def lint(path: str) -> str:
    """Run ruff linter on a Python file. Returns issues or 'No lint issues found'."""
    return lint_file(path)


if __name__ == "__main__":
    mcp.run()
