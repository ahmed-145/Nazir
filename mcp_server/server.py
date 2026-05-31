"""
Nazir custom MCP server — Phase 2 + 5.

Tools exposed to Claude Code and Gemini CLI:
  Shell:   safe_run_command, ping_heartbeat
  Files:   safe_read_file, safe_write_file, list_dir
  Git:     git_status, git_diff, git_log, git_commit, git_add, git_stash, git_stash_pop
  Search:  search_in_files, find_files
  Code:    run_python, run_tests, lint_file
  Memory:  wrapup, catchup, update_claude_md   ← Phase 5

All file/path operations are validated against NAZIR_PROJECT_ROOT.
All shell commands are checked against the blocklist.
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
def run_command(cmd: str, cwd: str = None, timeout: int = 30, dry_run: bool = False) -> str:
    """
    Run a shell command inside PROJECT_ROOT.
    Blocked: rm -rf, mkfs, sudo, fork bombs, and other destructive patterns.
    cwd must be inside PROJECT_ROOT if provided.
    dry_run: if True, validates the command but does not execute it.
    """
    return safe_run_command(cmd, cwd, timeout, dry_run)


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


# ── Memory / Context Management (Phase 5) ────────────────────────────────────

@mcp.tool()
def wrapup(
    task: str,
    completed: list[str] = None,
    pending: list[str] = None,
    decisions: list[str] = None,
    files_modified: list[str] = None,
    blockers: list[str] = None,
) -> str:
    """
    Save a context checkpoint to memory/last_checkpoint.md.
    Call this at 65% context usage or before ending a session.
    Automatically includes active Gemini session UUIDs.

    Args:
        task:           What you are currently working on.
        completed:      Steps completed this session.
        pending:        Steps still to do (agent resumes here).
        decisions:      Key decisions made this session.
        files_modified: Files changed this session.
        blockers:       Current blockers or open questions.
    """
    from memory.wrapup import write_checkpoint
    from orchestrator.gemini_runner import ACTIVE_SESSIONS
    archive = write_checkpoint(
        task=task,
        completed=completed or [],
        pending=pending or [],
        decisions=decisions or [],
        files_modified=files_modified or [],
        blockers=blockers or [],
        gemini_sessions=dict(ACTIVE_SESSIONS),
    )
    return f"Checkpoint saved → {archive}"


@mcp.tool()
def catchup() -> str:
    """
    Restore context from memory/last_checkpoint.md at the start of a session.
    Loads Gemini session UUIDs and returns the full checkpoint text.
    Call this first thing every new session.
    """
    from memory.catchup import restore, summary
    context = restore()
    s = summary()
    header = (
        f"[Nazir catchup] Sessions restored: {s['sessions_count']} | "
        f"Checkpoint age: {s['checkpoint_age_seconds']}s\n\n"
    )
    return header + context


@mcp.tool()
def update_claude_md(
    decision: str = None,
    architecture: str = None,
    known_issues: list[str] = None,
) -> str:
    """
    Update CLAUDE.md sections after completing a task.
    Call this at the end of every task to keep the agent context file current.

    Args:
        decision:       One-line summary of what was done/decided (prepended to Recent Decisions).
        architecture:   Updated description of current architecture (replaces section).
        known_issues:   Current list of known issues/tech debt (replaces section).
    """
    from memory.updater import full_update
    from orchestrator.gemini_runner import ACTIVE_SESSIONS
    full_update(
        decision=decision,
        architecture=architecture,
        known_issues=known_issues,
        gemini_sessions=dict(ACTIVE_SESSIONS) if ACTIVE_SESSIONS else None,
    )
    updated = []
    if decision:      updated.append("Recent Decisions")
    if architecture:  updated.append("Current Architecture")
    if known_issues is not None: updated.append("Known Issues")
    return f"CLAUDE.md updated: {', '.join(updated) or 'no changes'}"


# ── Cost / Metrics (Phase 6) ──────────────────────────────────────────────────

@mcp.tool()
def cost_report(period: str = "week") -> str:
    """
    Show token delegation savings and estimated dollar cost avoided by using
    Gemini instead of Claude for bulk analysis and code generation.

    period: "today" | "week" | "month" | "all"

    Returns a formatted report with delegation count, tokens used,
    tokens avoided on Claude, estimated dollars saved, and top tasks.
    """
    from orchestrator.metrics import cost_report as _report, format_report
    return format_report(_report(period))


@mcp.tool()
def delegation_stats() -> str:
    """
    Return raw metrics summary as JSON. Useful for the dashboard and
    programmatic access to savings data.
    """
    from orchestrator.metrics import cost_report as _report
    import json
    return json.dumps(_report("all"), indent=2)


# ── Dashboard (Phase 7) ───────────────────────────────────────────────────────

@mcp.tool()
def dashboard_snapshot() -> str:
    """
    Return a JSON snapshot of the current dashboard state: heartbeat, agent
    status, active sessions, cost summary, current task, recent tasks.
    Useful for quick status checks without launching the TUI.
    """
    import json
    from dashboard.data import full_snapshot
    return json.dumps(full_snapshot(), indent=2)


@mcp.tool()
def export_dashboard(format: str = "html") -> str:
    """
    Export a static dashboard snapshot to file.

    format: "html" (self-contained HTML page, default) | "svg" (terminal screenshot)

    Returns the path to the exported file.
    """
    if format == "svg":
        from dashboard.export import export_svg
        path = export_svg()
    else:
        from dashboard.export import export_html
        path = export_html()
    return f"Exported → {path}"


# ── Subagents (Phase 8) ───────────────────────────────────────────────────────

@mcp.tool()
def run_agent(role: str, task: str, context_json: str = "{}") -> str:
    """
    Run a single named subagent role on a task.

    role: "planner" | "coder" | "tester" | "reviewer"
    task: description of what to do
    context_json: optional JSON string with extra context (e.g. plan, feedback)

    Returns the agent's output as text.
    """
    import json
    from orchestrator.agents import run_agent as _run, AgentError
    try:
        ctx = json.loads(context_json) if context_json.strip() else {}
        result = _run(role, task, ctx)
        lines = [
            f"Role: {result.role}",
            f"Success: {result.success}",
            f"Duration: {result.duration_s:.1f}s",
            f"Output:\n{result.output[:2000]}",
        ]
        if result.error:
            lines.append(f"Error: {result.error}")
        return "\n".join(lines)
    except AgentError as e:
        return f"AgentError: {e}"


@mcp.tool()
def run_pipeline(task: str, dry_run: bool = True, max_iterations: int = 3) -> str:
    """
    Run the full Nazir subagent pipeline on a task:
      plan → [code → test]* → review → commit

    task: the task to implement (be specific and self-contained)
    dry_run: if True (default), skips the final git commit — safe for testing
    max_iterations: maximum code→test retry loops (default 3)

    Returns a human-readable pipeline summary.
    """
    from orchestrator.agents import SubagentOrchestrator, pipeline_summary
    orch = SubagentOrchestrator()
    result = orch.run_pipeline(task, dry_run=dry_run, max_iterations=max_iterations)
    return pipeline_summary(result)


if __name__ == "__main__":
    mcp.run()
