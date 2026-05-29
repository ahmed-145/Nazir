#!/usr/bin/env python3
"""
CLAUDE.md auto-updater — Phase 5.

Updates specific sections of CLAUDE.md after each task:
  - Recent Decisions (prepend newest entry)
  - Current Architecture (full replace)
  - Known Issues / Tech Debt (full replace)
  - Active Gemini CLI Sessions (full replace)

Called by the agent after every completed task via the `update_claude_md` MCP tool.
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()

CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"


def _replace_section(content: str, section_header: str, new_body: str) -> str:
    """
    Replace the body of a markdown section with new_body.
    Preserves the header line and everything after the next ## header.
    """
    # Match: ## Section Header\n(body until next ##-level heading or end)
    pattern = rf"(## {re.escape(section_header)}\n)(.*?)(?=\n## |\Z)"
    replacement = rf"\g<1>{new_body.rstrip()}\n"
    return re.sub(pattern, replacement, content, flags=re.DOTALL)


def prepend_decision(decision: str, date: str = None) -> str:
    """
    Prepend a new entry to the Recent Decisions section.
    Returns the updated CLAUDE.md content.
    """
    if not CLAUDE_MD.exists():
        return ""

    date = date or datetime.now().strftime("%Y-%m-%d")
    content = CLAUDE_MD.read_text()

    # Find the Recent Decisions section and prepend
    section = "Recent Decisions"
    pattern = rf"(## {re.escape(section)}\n)"
    new_entry = f"- {date}: {decision}\n"
    replacement = rf"\g<1>{new_entry}"
    updated = re.sub(pattern, replacement, content, count=1)

    CLAUDE_MD.write_text(updated)
    return updated


def update_section(section_header: str, new_body: str) -> str:
    """
    Replace a section body in CLAUDE.md.
    Returns the updated content.
    """
    if not CLAUDE_MD.exists():
        return ""

    content = CLAUDE_MD.read_text()
    updated = _replace_section(content, section_header, new_body)
    CLAUDE_MD.write_text(updated)
    return updated


def update_architecture(description: str) -> str:
    """Update the Current Architecture section."""
    return update_section("Current Architecture", description)


def update_known_issues(issues: list[str]) -> str:
    """Update the Known Issues / Tech Debt section."""
    body = "\n".join(f"- {i}" for i in issues) if issues else "(none)"
    return update_section("Known Issues / Tech Debt", body)


def update_mcp_servers(servers: dict[str, str]) -> str:
    """
    Update the MCP Servers Available section.
    servers: {name: description}
    """
    lines = [f"- {name}: {desc}" for name, desc in servers.items()]
    return update_section("MCP Servers Available", "\n".join(lines))


def update_gemini_sessions(sessions: dict[str, str]) -> str:
    """Update Active Gemini CLI Sessions section."""
    if sessions:
        body = "\n".join(f"- {k}: {v[:16]}..." for k, v in sessions.items())
    else:
        body = "(none)"
    return update_section("Active Gemini CLI Sessions", body)


def full_update(
    decision: str = None,
    architecture: str = None,
    known_issues: list[str] = None,
    gemini_sessions: dict[str, str] = None,
) -> str:
    """
    Apply all updates in one call. Returns the final CLAUDE.md content.
    """
    if not CLAUDE_MD.exists():
        return "CLAUDE.md not found"

    content = CLAUDE_MD.read_text()

    if decision:
        date = datetime.now().strftime("%Y-%m-%d")
        pattern = r"(## Recent Decisions\n)"
        content = re.sub(pattern, rf"\g<1>- {date}: {decision}\n", content, count=1)

    if architecture:
        content = _replace_section(content, "Current Architecture", architecture)

    if known_issues is not None:
        body = "\n".join(f"- {i}" for i in known_issues) or "(none)"
        content = _replace_section(content, "Known Issues / Tech Debt", body)

    if gemini_sessions is not None:
        body = "\n".join(f"- {k}: {v[:16]}..." for k, v in gemini_sessions.items()) or "(none)"
        content = _replace_section(content, "Active Gemini CLI Sessions", body)

    CLAUDE_MD.write_text(content)
    return content


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        full_update(decision=" ".join(sys.argv[1:]))
        print(f"[Nazir updater] CLAUDE.md updated.")
    else:
        print("Usage: python3 memory/updater.py 'decision text'")
