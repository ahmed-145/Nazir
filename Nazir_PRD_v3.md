# Nazir — Product Requirements Document
### Linux-Native AI Agent Platform | v3.0 | May 2026
### Built for: Pop!_OS 22.04 · GNOME 42 · Claude Code + Gemini CLI + Antigravity 2.0 CLI

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Lessons From Research](#2-lessons-from-research)
3. [System Architecture](#3-system-architecture)
4. [Full Tech Stack](#4-full-tech-stack)
5. [Directory Structure](#5-directory-structure)
6. [Build Phases](#6-build-phases)
7. [CLAUDE.md Specification](#7-claudemd-specification)
8. [Context Management Strategy](#8-context-management-strategy)
9. [systemd Deployment](#9-systemd-deployment)
10. [Security Model](#10-security-model)
11. [Infrastructure & Cost](#11-infrastructure--cost)
12. [Milestones & Timeline](#12-milestones--timeline)
13. [Failure Modes & Mitigations](#13-failure-modes--mitigations)
14. [Open Questions](#14-open-questions)
15. [First Actions Before Building](#15-first-actions-before-building)

---

## 1. Executive Summary

**Nazir** is a Linux-native autonomous AI agent platform running on Pop!_OS 22.04 with GNOME 42. It uses **Claude Code as the orchestrator brain** and either **Gemini CLI or the official Antigravity 2.0 CLI as the execution hands**, with the backend chosen empirically by the Phase 0.5 probe before any code is written.

The platform is designed around five core principles:

1. **Don't fight the OS** — GNOME 42 has no Newton accessibility, Wayland blocks most GUI automation. Nazir works through CLI, APIs, and filesystem only.
2. **Security first, then features** — DesktopCommanderMCP has active ecosystem-level MCP vulnerabilities, Gemini CLI runs with --yolo. Every tool is hardened before use.
3. **Design for context amnesia** — Claude Code's context window will fill up. The architecture treats context as ephemeral RAM and the filesystem as persistent memory from day one.
4. **Measure before you build** — The Phase 0.5 probe empirically verifies every load-bearing API behavior before any Phase 1+ code is written. Never write code against an assumption you haven't confirmed.
5. **Execution backend is swappable** — Gemini CLI and the official Antigravity 2.0 CLI are both viable automation surfaces. The architecture abstracts over both; probe results decide which one runs.

| Dimension | Capability |
|---|---|
| Brain | Claude Code (orchestrator, planner, reviewer) |
| Hands | Gemini CLI --yolo **or** Antigravity 2.0 CLI (decided by probe) |
| Body | DesktopCommanderMCP (hardened) + custom Python MCP server |
| Sync | cgcone or AgentLink (MCP config sync across both CLIs) |
| Persistence | systemd + heartbeat daemon with git rollback (redesigned — see §9) |
| Memory | CLAUDE.md single source of truth + filesystem checkpoints |
| Remote | Tailscale + local FastAPI (replaces Heroku SSE relay — simpler, free, no cold starts) |
| OS | Pop!_OS 22.04, GNOME 42, pop-shell tiling WM |

---

## 2. Lessons From Research

Five rounds of deep research (v1 April, v2 May, v3 May 2026 post-I/O verification). These constraints are non-negotiable unless explicitly marked as updated.

### 2.1 What We Are NOT Building (and Why)

| Abandoned Approach | Why |
|---|---|
| GUI automation via gnome-desktop-mcp | Requires GNOME unsafe_mode — collapses all Wayland security |
| pyautogui for mouse/keyboard | Completely broken on Wayland, maintainers won't fix it |
| xdotool / wmctrl | X11 only, dead on Wayland |
| Newton AT-SPI2 | Requires GNOME 46+ — not available on GNOME 42 |
| OpenClaw as gateway | CVE-2026-25253 RCE + Google mass-banned users who routed via it (confirmed May 2026) |
| Railway for relay hosting | Free tier eliminated in 2026, only $5 trial credit |
| WebSocket for relay | SSE is more reliable, auto-reconnects, no protocol upgrade needed |
| Auto Mode for systemd | Burns tokens alarmingly, community consensus against it |
| CodeConductor | Commercial SaaS, "Clawjacked" supply chain attack in 2026 |
| AionUi as primary interface | 3 active critical bugs: auth failure, rate limiting, file binding |
| Antigravity via third-party proxy in daemon loops | OpenClaw routing → Google account ban (real event, May 2026) |
| GEMINI.md separate context file | "Context Hell" — use CLAUDE.md as single source of truth for both agents |
| Multiple API keys for more Gemini quota | Rate limits are per project not per key — more keys = same quota |
| Heroku SSE relay | Replaced by Tailscale + local FastAPI — simpler, encrypted, always-on, $0 |
| Anthropic OSS grant for daemon funding | Grant requires 5,000+ GitHub stars — Nazir has zero. Also: grant = personal Claude Max subscription, NOT API access. Cannot fund automated pipelines. |

### 2.2 What We ARE Building (and Why)

| Chosen Approach | Why |
|---|---|
| CLI + API + filesystem only | Works perfectly on GNOME 42, no Wayland restrictions |
| Gemini CLI as primary execution backend | Official, supported, Pro = Gemini 2.5 Pro + 1M context, --yolo flag for automation |
| Antigravity 2.0 CLI as alternate backend | Official CLI/SDK launched I/O May 2026 — automation-blessed, quota tripled May 21 2026 |
| Phase 0.5 probe to pick the backend | Empirically benchmark both before committing. Quota numbers change weekly. |
| Context funneling via @directory syntax | Claude delegates file analysis to Gemini CLI, preserves Claude's context window |
| Session persistence via --resume + UUID | Gemini CLI maintains state. UUID scraped from filesystem (not JSON stdout — issue #14435) |
| GOOGLE_API_KEY env var (not OAuth) | Bypasses GNOME keyring failure in daemon/headless mode |
| DesktopCommanderMCP (hardened) | Terminal MCP with AppArmor named profile + path validation |
| Claude Code --dangerously-skip-permissions | Inside isolated project scope, community consensus for daemon use |
| Gemini CLI --yolo + policy TOML | Full automation without interactive prompts, with command whitelist/blacklist |
| cgcone or AgentLink for MCP sync | Atomic cross-platform MCP config sync — one command installs MCP on both CLIs |
| CLAUDE.md as single source of truth | Gemini CLI reads it via contextFileName override in settings.json |
| Tailscale for remote access | Replaces Heroku relay — free, encrypted, no auth complexity, no cold starts |
| systemd + task-loop wrapper (not one-shot) | claude -p is a one-shot that exits 0. Needs a wrapper loop to re-run on next task. |
| Filesystem checkpoints (/wrapup + /catchup) | Solves context amnesia systematically |
| Telemetry disabled on Gemini CLI | Prevents proprietary code exfiltration to Google |
| NAZIR_PROJECT_ROOT env var | Single source for all paths — no more hardcoded /home/ahmed/nazir |

---

## 3. System Architecture

### 3.1 The Three-Layer Model

```
YOU (describe a task)
        ↓
Claude Code (BRAIN — plans, reasons, reviews, decides)
        ↓ calls via shell when needed
┌─────────────────────────────────────────────────┐
│  Execution Backend (abstracted — pick one)      │
│                                                 │
│  Option A: Gemini CLI --yolo --resume           │
│    → @dir/ syntax, 1M context, GOOGLE_API_KEY   │
│                                                 │
│  Option B: Antigravity 2.0 CLI (official)       │
│    → I/O May 2026, automation-blessed, 9× quota │
│                                                 │
│  Decided by probe_phase0_5.py results           │
└─────────────────────────────────────────────────┘
        ↓
DesktopCommanderMCP (BODY — terminal, git, process control)
        ↓
Your Pop!_OS filesystem and terminal
```

### 3.2 Full Component Map

| Component | Role | Stack | Notes |
|---|---|---|---|
| Claude Code CLI | Orchestrator brain, planner, reviewer | Anthropic CLI | --dangerously-skip-permissions in daemon |
| Gemini CLI | Execution subagent, file analysis | Node.js 20+, Google AI Pro | --yolo, --resume, GOOGLE_API_KEY |
| Antigravity 2.0 CLI | Alternate execution backend | Official Google CLI | Launched I/O May 2026. Quota-governed. |
| DesktopCommanderMCP | Terminal control, file ops, shell | Node.js, Stdio transport | AppArmor *named profile* (not /usr/bin/node) |
| Custom Python MCP | Git, code runner, search, heartbeat | Python, mcp SDK | Path validation, blocklist |
| cgcone / AgentLink | MCP config sync across both CLIs | CLI tool | Run once per new MCP server |
| systemd services | Process persistence, auto-restart | Linux systemd | task-loop wrapper, not bare claude -p |
| Heartbeat daemon | Cognitive loop detection, recovery | Python | systemctl --user services |
| Tailscale + FastAPI | Phone-to-PC bridge (optional Phase 6) | Python, Tailscale | Replaces Heroku SSE relay |
| CLAUDE.md | Single source of truth for both agents | Markdown | Auto-updated by Claude after each session |

### 3.3 Context Funneling — The Key Technique

Instead of Claude Code reading an entire codebase (burning its expensive context), it delegates to Gemini CLI:

```python
# Claude Code calls Gemini CLI for bulk analysis:
import subprocess, json

def analyze_codebase(query: str) -> str:
    result = subprocess.run([
        "gemini", "--yolo", "--output-format", "json",
        "-p", f"@src/ @tests/ @docs/ {query}"
    ], capture_output=True, text=True, env={
        **__import__("os").environ,
        "GEMINI_TELEMETRY_ENABLED": "false",
        "GEMINI_TELEMETRY_TARGET": "local",
    })
    try:
        return json.loads(result.stdout).get("response", result.stdout)
    except json.JSONDecodeError:
        return result.stdout

summary = analyze_codebase("Find all API endpoints and their dependencies")
# Claude uses this summary for planning — never reads raw files itself
```

Gemini's 1M token context handles the entire codebase. Claude gets a condensed summary.

### 3.4 Agent Loop (Normal Operation)

```
1. Task arrives (terminal input, current_task.md, or Tailscale remote)
2. Claude Code reads CLAUDE.md — loads full project context
3. Claude Code reads memory/last_checkpoint.md — where we left off
4. Claude Code plans task, breaks into subtasks
5. For each subtask:
   a. Large file/codebase analysis → spawn execution backend with @dir/ syntax
   b. Code generation → spawn execution backend with --resume UUID
   c. Terminal/git ops → call DesktopCommanderMCP
   d. Complex reasoning/review → Claude handles directly
6. Claude reviews all execution backend output before accepting
7. Runs tests via DesktopCommanderMCP shell tool
8. If error → captures stderr, feeds back to loop
9. Heartbeat file touched after each subtask
10. At 65% context → write /wrapup checkpoint, continue
11. On task complete → update CLAUDE.md Recent Decisions
12. git commit with descriptive message
13. Task loop wrapper reads next task from current_task.md
```

### 3.5 Gemini CLI Subprocess Management

```python
# orchestrator/gemini_runner.py
import subprocess, json, os
from pathlib import Path

PROJECT_ROOT = Path(os.environ["NAZIR_PROJECT_ROOT"])
SESSIONS_DIR = Path.home() / ".gemini" / "sessions"
ACTIVE_SESSIONS: dict[str, str] = {}  # task_name → session_uuid


def _scrape_latest_session_uuid() -> str | None:
    """
    Workaround for GitHub issue #14435:
    Gemini CLI does not include sessionId in --output-format json stdout yet.
    We read it from the filesystem instead: ~/.gemini/sessions/<hash>/*.jsonl
    Returns the UUID of the most recently modified session file.
    """
    files = list(SESSIONS_DIR.glob("**/*.jsonl"))
    if not files:
        return None
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return latest.stem  # filename without extension = session UUID


def run_gemini(prompt: str, task_name: str = None, new_session: bool = False) -> str:
    cmd = ["gemini", "--yolo", "--output-format", "json"]

    if task_name and task_name in ACTIVE_SESSIONS and not new_session:
        cmd += ["--resume", ACTIVE_SESSIONS[task_name]]

    cmd += ["-p", prompt]

    env = {
        **os.environ,
        "GOOGLE_API_KEY": os.environ["GOOGLE_API_KEY"],
        "GEMINI_TELEMETRY_ENABLED": "false",
        "GEMINI_TELEMETRY_TARGET": "local",
    }

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        env=env, timeout=120,
        cwd=str(PROJECT_ROOT)
    )

    # Handle exit codes (ranges confirmed by Gemini CLI troubleshooting docs)
    # Exact per-code semantics — verify with probe_phase0_5.py before relying on them
    if result.returncode == 41:
        raise RuntimeError("Gemini auth failed — check GOOGLE_API_KEY")
    if result.returncode not in (0, 41):
        # On any non-zero: attempt to capture UUID before re-raising
        uuid = _scrape_latest_session_uuid()
        if uuid and task_name:
            ACTIVE_SESSIONS[task_name] = uuid
        raise RuntimeError(
            f"Gemini exit {result.returncode}: {result.stderr[:200]}"
        )

    # Capture session UUID from filesystem (workaround for #14435)
    uuid = _scrape_latest_session_uuid()
    if uuid and task_name:
        ACTIVE_SESSIONS[task_name] = uuid

    try:
        data = json.loads(result.stdout)
        return data.get("response", result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def save_sessions(path: Path) -> None:
    path.write_text(json.dumps(ACTIVE_SESSIONS, indent=2))


def load_sessions(path: Path) -> None:
    if path.exists():
        ACTIVE_SESSIONS.update(json.loads(path.read_text()))


def check_quota() -> dict:
    result = subprocess.run(
        ["gemini", "--output-format", "json", "-p", "/stats"],
        capture_output=True, text=True,
        env={**os.environ, "GOOGLE_API_KEY": os.environ["GOOGLE_API_KEY"]}
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
```

### 3.6 Recovery Loop (Failure State)

```
1. Heartbeat daemon detects stale heartbeat (>5 min)
2. Daemon writes RECOVERY_MODE to memory/current_task.md
3. Daemon calls: systemctl --user restart claude-agent.service
   (NOT systemctl restart — user process cannot manage system services)
4. Task-loop wrapper picks up new current_task.md on next iteration
5. Agent reads last_checkpoint.md → resumes from last stable state
6. Agent attempts task with different strategy
7. If 3 consecutive failures → daemon notifies via notify-send and pauses
```

---

## 4. Full Tech Stack

### 4.1 System Requirements & Setup

```bash
gnome-shell --version     # Should show 42.x
python3 --version         # Need 3.10+
claude --version          # Claude Code CLI

# Node.js 20+ is required for Gemini CLI
# Pop!_OS 22.04 ships older Node — install via nvm first
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 20 && nvm use 20 && nvm alias default 20
node --version            # Should show 20.x+
```

### 4.2 Gemini CLI Installation

```bash
npm install -g @google/gemini-cli
gemini --version

# Use API key (NOT OAuth) — OAuth breaks in headless/daemon mode
echo 'export GOOGLE_API_KEY="your-key-from-aistudio.google.com"' >> ~/.bashrc
echo 'export GEMINI_TELEMETRY_ENABLED=false' >> ~/.bashrc
echo 'export GEMINI_TELEMETRY_TARGET=local' >> ~/.bashrc
echo 'export NAZIR_PROJECT_ROOT="/home/ahmeed/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir"' >> ~/.bashrc
source ~/.bashrc

# Test headless mode
gemini --yolo -p "say hello" --output-format json
```

### 4.3 Gemini CLI Configuration

```json
// ~/.gemini/settings.json
{
  "defaultApprovalMode": "auto_edit",
  "telemetry": {
    "enabled": false,
    "target": "local"
  },
  "contextFileName": "CLAUDE.md"
}
```

Note: Do not set `"yolo": true` AND `"defaultApprovalMode": "auto_edit"` — they are contradictory. Use `--yolo` flag on the command line when needed.

### 4.4 Gemini CLI Policy Engine (Security)

```toml
# ~/.gemini/policies/safe-commands.toml
# Allowlist approach is more secure than blocklist-only.
# Highest-priority rule wins when multiple match.

[[rules]]
priority = 100
tool = "run_shell_command"
prefix = "git "
decision = "allow"

[[rules]]
priority = 100
tool = "run_shell_command"
prefix = "ls"
decision = "allow"

[[rules]]
priority = 100
tool = "run_shell_command"
prefix = "cat "
decision = "allow"

[[rules]]
priority = 100
tool = "run_shell_command"
prefix = "grep "
decision = "allow"

[[rules]]
priority = 100
tool = "run_shell_command"
prefix = "python3 "
decision = "allow"

[[rules]]
priority = 999
tool = "run_shell_command"
prefix = "rm -rf"
decision = "block"

[[rules]]
priority = 999
tool = "run_shell_command"
prefix = "curl"
decision = "block"

[[rules]]
priority = 999
tool = "run_shell_command"
prefix = "wget"
decision = "block"

[[rules]]
priority = 999
tool = "run_shell_command"
prefix = "sudo"
decision = "block"
```

### 4.5 MCP Sync with cgcone / AgentLink

```bash
# Option A: cgcone (real package name is @cgcone/cli)
npm install -g @cgcone/cli
cgcone install @wonderwhy-er/desktop-commander
cgcone install $NAZIR_PROJECT_ROOT/mcp_server/server.py

# Option B: AgentLink (fallback if cgcone is unavailable)
npm install -g agentlink
agentlink sync
```

### 4.6 Python Dependencies

```bash
pip install mcp                    # MCP server SDK
pip install fastapi uvicorn        # Remote access server (Tailscale-gated)
pip install aiofiles               # Async file I/O
pip install python-dotenv          # .env management
pip install gitpython              # Git operations for heartbeat daemon
pip install tenacity               # Exponential backoff for 429 handling
pip install watchdog               # File system watching for heartbeat
```

### 4.7 Execution Backend Options (decided by probe)

**Option A — Gemini CLI (recommended starting point)**
- Official, stable, proven headless mode
- 1M token context, `@dir/` syntax for bulk file analysis
- `GOOGLE_API_KEY` auth (no OAuth, works headless)
- Known gap: sessionId not yet in JSON stdout — scrape from filesystem (workaround in §3.5)

**Option B — Antigravity 2.0 CLI (evaluate in probe)**
- Official CLI + SDK launched at Google I/O May 19 2026
- Automation-blessed by Google (third-party proxies still banned, official CLI is fine)
- Quota tripled twice in one week May 21 2026 (9× launch-day levels) — currently generous
- Still new (~10 days old at PRD v3 writing) — expect rough edges, check syntax in probe
- Useful if Gemini CLI quota runs out: different quota pool

**The call:** Run `python3 probe_phase0_5.py`. Read `memory/probe_report.md`. Use whatever works.

---

## 5. Directory Structure

```
nazir/
  orchestrator/
    agent.py               ← Main orchestration logic
    gemini_runner.py       ← Gemini CLI subprocess manager (sessions, retry, quota)
    antigravity_runner.py  ← Antigravity 2.0 CLI runner (if chosen by probe)
    quota_monitor.py       ← Check quota before heavy tasks, trigger failover
    task_queue.py          ← Reads current_task.md, writes completed tasks to log
  mcp_server/
    server.py              ← Custom Python MCP server
    tools/
      files.py             ← safe_read_file, safe_write_file, list_dir
      shell.py             ← safe_run_command (blocklist checked)
      git.py               ← git_status, git_diff, git_commit, git_log
      code.py              ← run_python, run_tests, lint_file
      search.py            ← search_in_files (ripgrep), find_files
      heartbeat.py         ← ping_heartbeat (touches /tmp/nazir-heartbeat)
    config.py              ← NAZIR_PROJECT_ROOT, allowed_paths, blocklist
  heartbeat/
    daemon.py              ← Heartbeat monitor, recovery orchestrator
    rollback.py            ← git stash + rollback logic
    notify.py              ← Desktop notification on failure (notify-send)
  relay/                   ← Phase 6 only (Tailscale-gated FastAPI)
    main.py                ← FastAPI server (listens on Tailscale IP only)
    auth.py                ← Simple token auth
    queue.py               ← SQLite task queue
    models.py              ← Pydantic schemas
  memory/
    last_checkpoint.md     ← Current task state (read on every session start)
    current_task.md        ← What to do now (read by task-loop wrapper)
    gemini_sessions.json   ← Active session UUIDs (persisted across restarts)
    probe_results.json     ← Output of probe_phase0_5.py
    probe_report.md        ← Human-readable probe summary
    checkpoints/           ← Archived checkpoint history
  systemd/
    claude-agent.service   ← systemd --user unit for Claude Code
    heartbeat.service      ← systemd --user unit for heartbeat daemon
    run-claude.sh          ← Task-loop wrapper (sources nvm, loops on current_task.md)
  security/
    apparmor/
      nazir-desktop-cmd    ← Named AppArmor profile (NOT /usr/bin/node — too broad)
    validate_path.py       ← Path traversal prevention
    blocklist.py           ← Command blocklist
  probe_phase0_5.py        ← Run before Phase 1 — verifies all assumptions
  CLAUDE.md                ← Single source of truth (both Claude + Gemini read this)
  CLAUDE.local.md          ← Local overrides, never committed
  AGENTS.md                ← Subagent definitions and delegation rules
  .geminiignore            ← Prevents Gemini MemoryDiscovery scanning node_modules etc
  .env.example             ← Template
  .env                     ← Real keys (gitignored — never paste in chat)
  config.yaml              ← Main config
  requirements.txt
  README.md
  .gitignore
```

### Critical: .geminiignore

```
node_modules/
.git/
venv/
__pycache__/
*.pyc
logs/
dist/
build/
.env
*.env
memory/_probe_tmp/
```

### Critical: NAZIR_PROJECT_ROOT

Every path in every file must use this env var, not a hardcoded string.

```python
# config.py
import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent  # fallback: repo root
)).resolve()
```

---

## 6. Build Phases

Build one phase at a time. Test before moving on.

---

### Phase 0 — Foundation ✅ COMPLETE

Repo initialized, Gemini CLI installed and confirmed headless with `--yolo` and API key auth. `.geminiignore` in place.

---

### Phase 0.5 — Assumption Probe (Before Any Code)

**Why this exists:** PRD v1 and v2 made several assumptions about Gemini CLI behavior that turned out to be wrong or unconfirmed. This phase replaces guesses with measurements.

**Run it:**
```bash
python3 probe_phase0_5.py
cat memory/probe_report.md
```

**What it tests:**

| Test | Why it matters |
|---|---|
| Gemini `-p` headless | Basic sanity |
| `--output-format json` parses | Your runner depends on this |
| JSON contains `sessionId` (#14435) | If missing, use filesystem scrape workaround |
| `--resume <uuid>` works headless | Session continuity for long tasks |
| Exit code on bad API key | PRD claims 41 — verify before depending on it |
| Policy TOML dir exists | Security layer 4 |
| `contextFileName` = CLAUDE.md | Gemini reads your project context |
| Antigravity 2.0 CLI available | New option as of I/O May 2026 |
| Antigravity headless works | If available, benchmark vs Gemini CLI |
| `claude -p` completes a task | Basic headless sanity |
| `claude -p` survives 20+ seconds | Known SIGTERM bug #29642 — affects daemon design |
| `.geminiignore` exists | Quota protection |
| `NAZIR_PROJECT_ROOT` set | Path sanity |

**Do not start Phase 1 until this report is green (or you understand every yellow/red).**

---

### Phase 1 — Hardened DesktopCommanderMCP (Days 1-2)

**Goal:** Terminal and filesystem control for Claude Code, secured against active MCP ecosystem vulnerabilities.

**AppArmor — use a named profile, not /usr/bin/node:**

The PRD v2 profile attached to `/usr/bin/node` which covers every node process on the system including Gemini CLI and npx. Use a named profile instead:

```
# /etc/apparmor.d/nazir-desktop-cmd
#include <tunables/global>

profile nazir-desktop-cmd {
  #include <abstractions/base>

  # Allow the desktop-commander node binary specifically
  /home/*/.nvm/versions/node/*/bin/node r,
  /home/*/.nvm/versions/node/*/bin/node ix,

  # Project root only
  @{NAZIR_PROJECT_ROOT}/** r,
  @{NAZIR_PROJECT_ROOT}/** w,

  # Temp files
  /tmp/nazir-** rw,

  # Block sensitive paths
  deny /etc/** w,
  deny /usr/** w,
  deny /root/** rw,
  deny /home/*/.ssh/** rw,
  deny /home/*/.gnupg/** rw,

  network tcp,
}
```

Note: AppArmor variables (`@{NAZIR_PROJECT_ROOT}`) require a tunable definition. Alternative: use a container.

**Install and connect:**
```bash
sudo apt install apparmor-utils
sudo aa-enforce /etc/apparmor.d/nazir-desktop-cmd

# Stdio transport (not SSE — avoids port conflicts)
claude mcp add desktop-commander \
  -- npx -y @wonderwhy-er/desktop-commander

# Sync to Gemini CLI
cgcone install @wonderwhy-er/desktop-commander
```

**Test:** Ask Claude Code to read a file, run `echo hello`, attempt to write outside PROJECT_ROOT (should be blocked).

---

### Phase 2 — Custom Python MCP Server (Days 2-3)

**Goal:** Project-specific tools with path and command security built in.

```python
# config.py
import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
```

```python
# security/validate_path.py
from pathlib import Path
from config import PROJECT_ROOT

def validate_path(requested: str) -> Path:
    resolved = Path(requested).resolve()
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        raise PermissionError(f"Path outside PROJECT_ROOT: {resolved}")
    return resolved
```

```python
# security/blocklist.py
BLOCKED_PATTERNS = [
    "rm -rf /", "rm -rf ~", "rm -rf *",
    "format c:", "mkfs", "dd if=/dev/zero",
    "> /dev/sda", "chmod -R 777 /",
    "sudo rm", "sudo mkfs",
    ":(){:|:&};:",
]

def check_command(cmd: str) -> None:
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd.lower():
            raise PermissionError(f"Blocked command: {pattern}")
```

```python
# mcp_server/tools/shell.py
from security.validate_path import validate_path
from security.blocklist import check_command
import subprocess

@mcp_tool
def safe_run_command(cmd: str, cwd: str = None) -> str:
    check_command(cmd)
    resolved_cwd = str(validate_path(cwd)) if cwd else None
    result = subprocess.run(
        cmd, shell=True, capture_output=True,
        text=True, cwd=resolved_cwd
    )
    return result.stdout + result.stderr

@mcp_tool
def ping_heartbeat() -> str:
    Path("/tmp/nazir-heartbeat").touch()
    return "heartbeat ok"
```

**Register:**
```bash
cgcone install $NAZIR_PROJECT_ROOT/mcp_server/server.py
```

**Test:** Path validation rejects writes outside PROJECT_ROOT. Blocklist rejects `rm -rf`. Heartbeat file gets touched.

---

### Phase 3 — Execution Backend Layer (Days 3-4)

**Goal:** Claude Code can delegate tasks to the chosen execution backend.

**3A. Build gemini_runner.py** (see §3.5 — full implementation with filesystem UUID scrape)

**3B. Build antigravity_runner.py** (if Antigravity CLI chosen by probe):

```python
# orchestrator/antigravity_runner.py
# NOTE: Fill in actual CLI syntax after running probe_phase0_5.py
# Antigravity 2.0 CLI is 10 days old at PRD v3 writing — syntax may shift.
import subprocess, json, os
from pathlib import Path
from config import PROJECT_ROOT

def run_antigravity(prompt: str) -> str:
    """Run a prompt via the official Antigravity 2.0 CLI."""
    # Actual flag syntax TBD from probe results — examples:
    # antigravity run --prompt "..."
    # antigravity -p "..."
    cmd = ["antigravity", "run", "--prompt", prompt]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=120, cwd=str(PROJECT_ROOT)
    )
    if result.returncode != 0:
        raise RuntimeError(f"Antigravity exit {result.returncode}: {result.stderr[:200]}")
    try:
        data = json.loads(result.stdout)
        return data.get("response", result.stdout)
    except json.JSONDecodeError:
        return result.stdout
```

**3C. Build quota_monitor.py:**

```python
# orchestrator/quota_monitor.py
from gemini_runner import check_quota

def should_use_gemini() -> bool:
    stats = check_quota()
    remaining = stats.get("remainingRequests", 100)
    if remaining < 50:
        print(f"[Nazir] Gemini quota low ({remaining}) — consider Antigravity CLI")
        return False
    return True
```

**Configure CLAUDE.md delegation rules:**
```markdown
## Execution Backend
Delegate to Gemini CLI (or Antigravity CLI if configured) when:
- Analyzing more than 3 files simultaneously
- Generating more than 200 lines of code
- Any task consuming >20% of your context

# Gemini CLI:
gemini --yolo --output-format json -p "@src/ @tests/ YOUR_QUERY"

# After each call, scrape UUID from ~/.gemini/sessions/ and save to memory/gemini_sessions.json
```

**Test:** Give Claude Code a task requiring 10+ file reads. Confirm it spawns the backend subprocess, gets summary back, uses it for planning.

---

### Phase 4 — Heartbeat Daemon + systemd (Days 4-5)

**Goal:** Nazir survives reboots, recovers from cognitive loops.

**Key design changes from PRD v2:**
- Use `systemctl --user` — a user process cannot manage system services
- The `claude -p` ExecStart is a **one-shot** (exits 0 on task completion). Use a task-loop wrapper
- Recovery: daemon writes to `current_task.md` and restarts the service, not `pkill` + Popen

**Task-loop wrapper:**
```bash
#!/bin/bash
# systemd/run-claude.sh
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
source "$NAZIR_PROJECT_ROOT/.env"
cd "$NAZIR_PROJECT_ROOT"

# Loop: read next task, run claude, repeat
while true; do
    TASK=$(cat memory/current_task.md 2>/dev/null || echo "Read CLAUDE.md and await task")
    if [ "$TASK" = "PAUSE" ]; then
        echo "[Nazir] Paused by heartbeat daemon. Waiting..."
        sleep 30
        continue
    fi
    claude --dangerously-skip-permissions -p "$TASK"
    EXIT_CODE=$?
    echo "[Nazir] Claude exited $EXIT_CODE at $(date)"
    # Brief pause before polling for next task
    sleep 5
done
```

**Heartbeat daemon:**
```python
# heartbeat/daemon.py
import time, subprocess, os
from pathlib import Path

HEARTBEAT_FILE = Path("/tmp/nazir-heartbeat")
TIMEOUT = 300
MAX_FAILURES = 3
PROJECT_ROOT = Path(os.environ["NAZIR_PROJECT_ROOT"])


def run():
    failures = 0
    while True:
        time.sleep(60)
        if HEARTBEAT_FILE.exists():
            age = time.time() - HEARTBEAT_FILE.stat().st_mtime
        else:
            age = 9999

        if age > TIMEOUT:
            failures += 1
            print(f"[Nazir Heartbeat] Stale ({age:.0f}s). Failure {failures}/{MAX_FAILURES}")

            if failures >= MAX_FAILURES:
                subprocess.run(["notify-send", "Nazir", "3 failures. Manual intervention needed."])
                # Write PAUSE to stop the task loop without killing it
                (PROJECT_ROOT / "memory" / "current_task.md").write_text("PAUSE")
                break

            # Stash partial work
            subprocess.run(["git", "stash"], cwd=str(PROJECT_ROOT))

            # Write recovery task
            checkpoint = PROJECT_ROOT / "memory" / "last_checkpoint.md"
            task = checkpoint.read_text() if checkpoint.exists() else "Resume last task from scratch"
            (PROJECT_ROOT / "memory" / "current_task.md").write_text(
                f"RECOVERY MODE. Read memory/last_checkpoint.md first.\n\n{task}"
            )

            # Restart via systemctl --user (user process can manage user services)
            subprocess.run(["systemctl", "--user", "restart", "claude-agent.service"])
        else:
            failures = 0


if __name__ == "__main__":
    run()
```

**systemd --user units:**
```ini
# ~/.config/systemd/user/claude-agent.service
[Unit]
Description=Nazir Claude Code Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir
ExecStart=%h/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir/systemd/run-claude.sh
Restart=on-failure
RestartSec=10
EnvironmentFile=%h/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir/.env
StandardOutput=append:%h/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir/logs/agent.log
StandardError=append:%h/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir/logs/agent.log

[Install]
WantedBy=default.target
```

```ini
# ~/.config/systemd/user/heartbeat.service
[Unit]
Description=Nazir Heartbeat Monitor
After=claude-agent.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir/heartbeat/daemon.py
Restart=always
EnvironmentFile=%h/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir/.env

[Install]
WantedBy=default.target
```

**Enable (no sudo required):**
```bash
mkdir -p ~/.config/systemd/user/ logs
cp systemd/claude-agent.service ~/.config/systemd/user/
cp systemd/heartbeat.service ~/.config/systemd/user/
chmod +x systemd/run-claude.sh
systemctl --user daemon-reload
systemctl --user enable claude-agent.service heartbeat.service
systemctl --user start heartbeat.service
# Enable linger so services survive logout
loginctl enable-linger $USER
```

**Test:** Kill the claude process manually. Confirm heartbeat detects it within 5 minutes and the task-loop restarts.

---

### Phase 5 — Context Management System (Days 5-6)

**Goal:** Context amnesia never causes task failure.

**Wrapup (called at 65% context):**
```python
# memory/wrapup.py
from datetime import datetime
from pathlib import Path
import json, os

PROJECT_ROOT = Path(os.environ["NAZIR_PROJECT_ROOT"])

def write_checkpoint(
    task: str,
    completed: list,
    pending: list,
    decisions: list,
    files_modified: list,
    blockers: list,
    gemini_sessions: dict = None
):
    content = f"""# Nazir Context Checkpoint
Generated: {datetime.now().isoformat()}

## Current Task
{task}

## Completed Steps
{chr(10).join(f'- {s}' for s in completed)}

## Pending (resume here)
{chr(10).join(f'- {s}' for s in pending)}

## Key Decisions Made
{chr(10).join(f'- {d}' for d in decisions)}

## Files Modified This Session
{chr(10).join(f'- {f}' for f in files_modified)}

## Blockers / Issues
{chr(10).join(f'- {b}' for b in blockers)}

## Active Sessions
{chr(10).join(f'- {k}: {v}' for k, v in (gemini_sessions or {}).items())}
"""
    (PROJECT_ROOT / "memory" / "last_checkpoint.md").write_text(content)
    archive_dir = PROJECT_ROOT / "memory" / "checkpoints"
    archive_dir.mkdir(exist_ok=True)
    (archive_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.md").write_text(content)

    if gemini_sessions:
        (PROJECT_ROOT / "memory" / "gemini_sessions.json").write_text(
            json.dumps(gemini_sessions, indent=2)
        )
```

**Catchup (on session start):**
```python
# memory/catchup.py
import json, os
from pathlib import Path

PROJECT_ROOT = Path(os.environ["NAZIR_PROJECT_ROOT"])

def restore() -> str:
    cp = PROJECT_ROOT / "memory" / "last_checkpoint.md"
    sessions_file = PROJECT_ROOT / "memory" / "gemini_sessions.json"

    context = cp.read_text() if cp.exists() else "No checkpoint. Starting fresh."

    if sessions_file.exists():
        from orchestrator.gemini_runner import ACTIVE_SESSIONS, load_sessions
        load_sessions(sessions_file)

    return context
```

**Test:** Force 65% context, confirm checkpoint fires. Restart session, confirm agent resumes from checkpoint with sessions intact.

---

### Phase 6 — Tailscale Remote Access (Days 6-7, Optional)

**Goal:** Send tasks from your phone from anywhere. Replaces Heroku SSE relay.

**Why Tailscale instead of Heroku:**
- Free for personal use, no cold starts, always-on
- End-to-end encrypted — no auth complexity needed on the FastAPI side
- Your phone just joins the tailnet via the Tailscale app
- No public exposure — server only listens on Tailscale IP

```bash
# Install Tailscale on both PC and phone
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Get your Tailscale IP
tailscale ip -4
```

```python
# relay/main.py — listens on Tailscale IP only
import os
from fastapi import FastAPI, Header, HTTPException
from pathlib import Path

app = FastAPI()
PROJECT_ROOT = Path(os.environ["NAZIR_PROJECT_ROOT"])
AUTH_TOKEN = os.environ["NAZIR_RELAY_TOKEN"]  # simple shared secret

@app.post("/task")
async def submit_task(body: dict, x_token: str = Header(...)):
    if x_token != AUTH_TOKEN:
        raise HTTPException(403)
    (PROJECT_ROOT / "memory" / "current_task.md").write_text(body["task"])
    return {"status": "queued"}

@app.get("/status")
async def get_status(x_token: str = Header(...)):
    if x_token != AUTH_TOKEN:
        raise HTTPException(403)
    cp = PROJECT_ROOT / "memory" / "last_checkpoint.md"
    return {"checkpoint": cp.read_text() if cp.exists() else "No checkpoint"}
```

```bash
# Run on Tailscale IP (not 0.0.0.0)
TAILSCALE_IP=$(tailscale ip -4)
uvicorn relay.main:app --host $TAILSCALE_IP --port 8765

# From your phone (also on Tailscale):
curl -X POST http://<tailscale-ip>:8765/task \
  -H "x-token: your-secret" \
  -H "Content-Type: application/json" \
  -d '{"task": "create test.txt with hello world"}'
```

---

### Phase 7 — Production Hardening (Days 7-12)

**Checklist:**
- [ ] AppArmor *named profile* active and tested (not /usr/bin/node)
- [ ] Gemini CLI policy TOML enforced — test with a blocked command
- [ ] .geminiignore in place — confirm quota doesn't spike on startup
- [ ] GEMINI_TELEMETRY_ENABLED=false — confirm in `gemini env` output
- [ ] Path validation tested with directory traversal (`../../etc/passwd`)
- [ ] Command blocklist tested with bypass patterns
- [ ] Checkpoint tested — fill context deliberately, confirm wrapup fires
- [ ] Heartbeat tested — kill process, confirm recovery within 5 min
- [ ] Task-loop wrapper tested — confirm it picks up next task after completion
- [ ] systemd --user services survive reboot (loginctl enable-linger set)
- [ ] Pre-commit hook active — no keys leak into commits
- [ ] NAZIR_PROJECT_ROOT set in .env and ~/.bashrc
- [ ] Logs rotate (logrotate config or journald limits set)
- [ ] probe_phase0_5.py still passes (re-run after each major change)

**Pre-commit hook:**
```bash
#!/bin/bash
# .git/hooks/pre-commit
if git diff --cached | grep -E "(GOOGLE_API_KEY|ANTHROPIC_API_KEY|sk-ant|AIza[A-Za-z0-9_-]{35})" ; then
    echo "ERROR: API key pattern detected in commit. Aborting."
    exit 1
fi
```

```bash
chmod +x .git/hooks/pre-commit
```

---

## 7. CLAUDE.md Specification

The agent reads this at the start of every session. It must reflect what's *actually built*.

```markdown
# Nazir — Agent Context File
Last Updated: [agent updates this after each session]
Version: 3.0

## Identity
You are Nazir's orchestrator. You think, plan, review, and decide.
The execution backend (Gemini CLI or Antigravity 2.0 CLI) writes code and analyzes files.
You never do heavy file reading or large code generation yourself.

## Environment
- OS: Pop!_OS 22.04, GNOME 42, pop-shell tiling WM
- Node.js: 20+ (via nvm)
- Python: 3.10+
- Project root: set via NAZIR_PROJECT_ROOT env var (never hardcode a path)

## Every Session — Do This First
1. Read memory/last_checkpoint.md
2. Read memory/current_task.md
3. Run: git status
4. Load session UUIDs: memory/gemini_sessions.json
5. Begin work

## Execution Backend Delegation Rules
Delegate when:
- Analyzing more than 3 files simultaneously
- Generating more than 200 lines of code
- Any task consuming >20% of your context

Gemini CLI:
  gemini --yolo --output-format json -p "@src/ @tests/ YOUR_QUERY"
  After each call: scrape UUID from ~/.gemini/sessions/ → save to memory/gemini_sessions.json

Antigravity 2.0 CLI (if installed):
  See orchestrator/antigravity_runner.py for current syntax

Always review output before accepting. Never commit without review.

## Context Management
- At 65% → call wrapup IMMEDIATELY
- Save session UUIDs in every checkpoint

## Path Rules
- Always use NAZIR_PROJECT_ROOT env var — never hardcode any path
- Never write files outside PROJECT_ROOT

## MCP Servers Available
[Updated by agent as phases complete]

## Heartbeat
- Touch /tmp/nazir-heartbeat after every subtask
- Daemon restarts you if it goes stale >5 min

## After Every Task
1. Write memory/last_checkpoint.md
2. git add + commit
3. Update Recent Decisions below
4. Update Current Architecture if it changed
5. Save session UUIDs to memory/gemini_sessions.json

## Recent Decisions
[agent appends here — newest first]

## Current Architecture
[agent maintains this]

## Known Issues / Tech Debt
[agent maintains this — honest list]

## Active Sessions
[agent maintains this — task_name → UUID]
```

---

## 8. Context Management Strategy

### 8.1 Three-Layer Memory Model

```
Layer 1: Context Window (ephemeral — treat like RAM)
  → Current reasoning, active conversation
  → NEVER rely on this for critical architectural decisions
  → Act at 65%, never wait for auto-compact

Layer 2: Filesystem (persistent — treat like SSD)
  → memory/last_checkpoint.md — current task state
  → memory/checkpoints/ — session archive
  → memory/gemini_sessions.json — session UUIDs
  → CLAUDE.md — project knowledge base
  → logs/ — execution history

Layer 3: Git History (permanent — treat like backup)
  → Every completed task = one descriptive commit
  → Heartbeat daemon triggers git stash on recovery
  → Full audit trail
```

### 8.2 Session UUID Lifecycle

```
New task requiring Gemini:
  → run_gemini(prompt, task_name="feature-x", new_session=True)
  → Call completes
  → _scrape_latest_session_uuid() reads ~/.gemini/sessions/**/*.jsonl
  → Most recently modified = our session UUID
  → Saved to ACTIVE_SESSIONS["feature-x"]

Follow-up:
  → run_gemini(prompt, task_name="feature-x")
  → Uses ACTIVE_SESSIONS["feature-x"] as --resume arg

Checkpoint:
  → gemini_sessions.json saved with every /wrapup

Recovery:
  → catchup.py re-injects UUIDs into ACTIVE_SESSIONS
  → Gemini continues with context intact
```

---

## 9. systemd Deployment

Use `systemctl --user` throughout. No sudo required, no system service conflicts.

### 9.1 Setup

```bash
mkdir -p ~/.config/systemd/user/ logs memory/checkpoints
cp systemd/claude-agent.service ~/.config/systemd/user/
cp systemd/heartbeat.service ~/.config/systemd/user/
chmod +x systemd/run-claude.sh
systemctl --user daemon-reload
systemctl --user enable claude-agent.service heartbeat.service
systemctl --user start heartbeat.service
loginctl enable-linger $USER  # survive logout
```

### 9.2 Monitoring

```bash
journalctl --user -u claude-agent.service -f
journalctl --user -u heartbeat.service -f
systemctl --user status heartbeat.service
systemctl --user restart claude-agent.service
systemctl --user stop claude-agent.service heartbeat.service
```

---

## 10. Security Model

### 10.1 Threat Model

| Threat | Likelihood | Mitigation |
|---|---|---|
| Prompt injection via malicious file | Medium | Gemini policy TOML blocks curl/wget; Claude validates before acting |
| Agent deletes wrong files | Low-Medium | AppArmor named profile + PROJECT_ROOT + blocklist |
| API key leaked in git | Low | Pre-commit hook (catches AIza... pattern) + .gitignore |
| MCP ecosystem RCE (Apr 2026 design vuln) | Active | AppArmor named profile, Stdio transport only, path validation |
| Gemini --yolo weaponized by prompt injection | Medium | Policy TOML whitelist, telemetry off |
| Context amnesia causes regressions | High | Checkpoint at 65%, git rollback in recovery |
| Infinite loop burning tokens | Medium | Heartbeat daemon + quota monitor |
| Gemini MemoryDiscovery quota burn | High | .geminiignore — must exist before first run |
| Third-party Antigravity proxy (OpenClaw) | Confirmed | Never use — Google mass-banned users May 2026 |
| Antigravity official CLI ToS | Low | Official CLI is automation-blessed since I/O 2026 |
| API key in chat history | Happened once | Never select .env content while in a chat session |

### 10.2 Security Layers

```
Layer 1: PROJECT_ROOT enforcement (validate_path.py) — uses NAZIR_PROJECT_ROOT
Layer 2: Command blocklist (blocklist.py)
Layer 3: AppArmor named profile (not /usr/bin/node)
Layer 4: Gemini CLI policy TOML (safe-commands.toml)
Layer 5: Telemetry disabled (GEMINI_TELEMETRY_ENABLED=false)
Layer 6: .geminiignore (prevents quota burn + data leakage)
Layer 7: Heartbeat daemon (cognitive loop detection)
Layer 8: Git history (always recoverable)
Layer 9: Pre-commit hook (no keys in commits)
Layer 10: Tailscale (remote access — no public exposure)
```

### 10.3 AppArmor Profile (Named — Not /usr/bin/node)

```
# /etc/apparmor.d/nazir-desktop-cmd
#include <tunables/global>

profile nazir-desktop-cmd flags=(attach_disconnected) {
  #include <abstractions/base>
  #include <abstractions/nameservice>

  # Node binary via nvm (adjust version as needed)
  /home/*/.nvm/versions/node/*/bin/node rix,

  # Desktop commander package files
  /home/*/.npm/** r,
  /home/*/.nvm/** r,

  # Project root read/write
  /home/ahmeed/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir/** rw,

  # Temp files
  /tmp/nazir-** rw,

  # Hard denies
  deny /etc/** w,
  deny /usr/** w,
  deny /root/** rw,
  deny /home/*/.ssh/** rw,
  deny /home/*/.gnupg/** rw,
  deny /home/*/.bashrc w,
  deny /home/*/.env* rw,

  network tcp,
}
```

---

## 11. Infrastructure & Cost

### 11.1 Full Cost Breakdown

| Component | Monthly Cost | Notes |
|---|---|---|
| Claude Pro | $20 | Already paying — funds the orchestrator brain |
| Gemini CLI | $0 | Google AI Pro already have — 1M context execution |
| Antigravity 2.0 CLI | $0 | Included in existing Google AI Pro subscription |
| DesktopCommanderMCP | $0 | Open source |
| Custom MCP server | $0 | You build it |
| cgcone / AgentLink | $0 | Open source |
| Tailscale | $0 | Free for personal use (up to 3 devices) |
| DigitalOcean | $0 | GitHub Student Pack ($200 credit) |
| MongoDB Atlas | $0 | GitHub Student Pack ($50 credit, if needed for memory layer) |

**Total new monthly cost: $0**

### 11.2 OSS Grant Reality Check

The Anthropic OSS grant is **not applicable** to Nazir at this stage:
- Requires 5,000+ GitHub stars or 1M+ monthly npm downloads (Nazir has zero)
- Grant = personal Claude Max 20x subscription, **not API access for automated pipelines**
- A daemon running `claude -p` is API/CLI usage — the grant explicitly covers personal interactive use

If Nazir grows to 5k+ stars, re-evaluate. For now, build within Claude Pro + Google AI Pro limits.

### 11.3 Token Economics

| Task | Handler | Cost |
|---|---|---|
| Complex reasoning, architecture | Claude (direct) | Claude Pro |
| Large file analysis (@dir/ syntax) | Gemini CLI | Google AI Pro |
| Bulk code generation | Gemini CLI or Antigravity CLI | Google AI Pro |
| Terminal ops, git, tests | DesktopCommanderMCP | Free |
| Quick small edits | Claude (direct) | Claude Pro |

Estimated Claude token savings vs pure Claude: **60-75%**

---

## 12. Milestones & Timeline

| Phase | Deliverable | Time | Key Test |
|---|---|---|---|
| 0 | Foundation ✅ | Day 1 | Gemini CLI headless --yolo works |
| 0.5 | Assumption probe | Day 1 | probe_report.md all green/understood |
| 1 | DesktopCommanderMCP hardened | Days 1-2 | Named AppArmor profile blocks writes outside PROJECT_ROOT |
| 2 | Custom Python MCP server | Days 2-3 | Path validation, blocklist, heartbeat all work |
| 3 | Execution backend layer | Days 3-4 | Claude delegates @src/ analysis, gets summary back |
| 4 | Heartbeat daemon + systemd --user | Days 4-5 | Kill process → auto-recovery within 5 min |
| 5 | Context management | Days 5-6 | 65% context → checkpoint fires, UUIDs survive restart |
| 6 | Tailscale remote access (optional) | Days 6-7 | curl from phone → task executes on PC |
| 7 | Production hardening | Days 7-12 | All security tests pass, survives reboot |

**Total to daily-driver: 8-12 focused days**

---

## 13. Failure Modes & Mitigations

| Failure | Impact | Mitigation |
|---|---|---|
| Gemini CLI 429 quota exhausted | Code gen pauses | quota_monitor.py detects early, failover to Antigravity CLI |
| Gemini session UUID lost | Subagent loses context | Filesystem scrape workaround + gemini_sessions.json in every checkpoint |
| `sessionId` absent from JSON (#14435) | runner.py can't resume | **Already mitigated** — §3.5 scrapes from ~/.gemini/sessions/ instead |
| Node.js version mismatch | Gemini CLI won't start | nvm enforced in run-claude.sh |
| GNOME keyring blocks Gemini CLI | Auth fails in daemon | GOOGLE_API_KEY env var bypasses keyring entirely |
| .geminiignore missing | MemoryDiscovery burns quota | Critical file — must exist before first gemini invocation |
| DesktopCommanderMCP exploit | Filesystem damage | Named AppArmor profile + PROJECT_ROOT + blocklist |
| Context amnesia mid-task | Agent loses context | Checkpoint at 65%, never rely on auto-compact |
| Heartbeat false alarm | Unnecessary recovery | 5-min timeout, 3 strikes before pause |
| `claude -p` exits 0 silently | Task loop stalls | Task-loop wrapper in run-claude.sh handles re-reads of current_task.md |
| `systemctl restart` from user process | Recovery fails silently | Use `systemctl --user restart` — confirmed works for user services |
| AppArmor on /usr/bin/node | Breaks Gemini CLI, npx | Use named profile scoped to desktop-commander only |
| Antigravity quota changes again | Backend unavailable | Abstract over both backends, switch in config.yaml |
| API key pasted in chat session | Key exposed to logs | Rotate immediately. Never select .env in editor while in a chat session. |
| Tailscale offline | No remote access | Local terminal always works — remote is optional |

---

## 14. Open Questions

| Question | Status | Decision Needed By |
|---|---|---|
| Gemini CLI vs Antigravity 2.0 CLI? | **Run probe_phase0_5.py** | Phase 0.5 |
| Does `--resume` work reliably in headless? | Probe will confirm | Phase 0.5 |
| Exact exit codes 41/53? | Probe will measure actual codes | Phase 0.5 |
| Antigravity 2.0 CLI headless syntax? | Very new — probe will find it | Phase 0.5 |
| Antigravity quota — stable enough to depend on? | Tripled 2× in one week — too volatile to hardcode | Phase 3 |
| cgcone vs AgentLink? | Both exist — try cgcone first | Phase 1 |
| Memory layer for long projects | Filesystem only vs Octopoda MCP vs SQLite | Phase 5 |
| Upgrade Pop!_OS to 24.04? | Unlocks GNOME 46, Newton AT-SPI2 for GUI reading | Long term |
| OSS grant viable? | **No — ineligible + wrong grant type** | Closed |
| Heroku for relay? | **No — replaced by Tailscale** | Closed |

---

## 15. First Actions Before Building

In exact order.

**1. Set NAZIR_PROJECT_ROOT (2 mins):**
```bash
echo 'export NAZIR_PROJECT_ROOT="/home/ahmeed/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir"' >> ~/.bashrc
source ~/.bashrc
echo $NAZIR_PROJECT_ROOT  # confirm
```

**2. Rotate any exposed API keys:**
If you ever selected text from `.env` while a chat session was open — rotate it. Takes 2 minutes at aistudio.google.com.

**3. Run the assumption probe (10-15 mins):**
```bash
cd $NAZIR_PROJECT_ROOT
python3 probe_phase0_5.py
cat memory/probe_report.md
```

**4. Read probe_report.md — understand every yellow/red before proceeding.**

**5. Claim GitHub Student Pack (10 mins):**
- education.github.com/pack → DigitalOcean $200, MongoDB $50 (Heroku not needed)

**6. Install Tailscale (5 mins, if you want remote access):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Install on phone too
```

**7. Phase 1: DesktopCommanderMCP** — only after probe is green.

**Total time before Phase 1 code: ~30 minutes.**

---

*Nazir PRD v3.0 — Built from 5 rounds of deep research + live verification (May 2026)*
*Pop!_OS 22.04 · GNOME 42 · Claude Code + Gemini CLI + Antigravity 2.0 CLI*
*v3 changes: Antigravity 2.0 CLI added as official backend option, OSS grant corrected,*
*6 PRD v2 code bugs fixed, systemd redesigned (user units + task-loop wrapper),*
*AppArmor scoped to named profile, Heroku replaced by Tailscale, Phase 0.5 probe added,*
*NAZIR_PROJECT_ROOT env var throughout, Tailscale remote replaces Heroku SSE relay*
