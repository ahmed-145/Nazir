# Nazir — Product Requirements Document
### Linux-Native AI Agent Platform | v4.0 | May 2026
### Built for: Pop!_OS 22.04 · GNOME 42 · Claude Code + Gemini CLI

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [What We Learned](#2-what-we-learned)
3. [System Architecture](#3-system-architecture)
4. [Full Tech Stack](#4-full-tech-stack)
5. [Directory Structure](#5-directory-structure)
6. [Build Phases 0–10](#6-build-phases-010)
7. [Context Management](#7-context-management)
8. [systemd Deployment](#8-systemd-deployment)
9. [Security Model](#9-security-model)
10. [Infrastructure & Cost](#10-infrastructure--cost)
11. [Milestones & Timeline](#11-milestones--timeline)
12. [Failure Modes & Mitigations](#12-failure-modes--mitigations)
13. [Open Questions](#13-open-questions)

---

## 1. Executive Summary

**Nazir** is a Linux-native AI agent platform that uses **Claude Code as the orchestrator brain** and **Gemini CLI as the execution hands**, connected through a hardened custom MCP server layer.

### What it is

A **token-saving orchestration layer for interactive development work** that:
- Routes large file analysis and bulk code generation to Gemini CLI's 1M-context window, sparing Claude's expensive context for reasoning and decisions
- Estimates and tracks the dollar savings from every delegation in real time
- Provides a terminal dashboard showing what's happening and what it's saving
- Is a genuinely interesting portfolio piece demonstrating multi-LLM agent architecture

### What it is not

An always-on autonomous daemon. That framing drove the first three PRD versions and created two unsolved problems — Claude Pro economics and unattended-write safety — that weren't worth solving for the actual use case. Daemon/unattended mode exists as an optional toggle (Phase 4 infrastructure is built), not the core product.

### North-star metric

> **Tokens delegated to Gemini → dollars saved vs Claude-only, cumulative.**

If that number is real, visible, and growing, Nazir is succeeding.

### Core principles (battle-tested through 5 rounds of research)

1. **Don't fight the OS.** GNOME 42 blocks GUI automation. Nazir is CLI + API + filesystem only.
2. **Measure before you build.** Phase 0.5 runs an assumption probe before any code is written. This caught 6 bugs in the v2 PRD.
3. **Security in layers, not single points.** Nine overlapping controls — none are sufficient alone.
4. **Execution backend is swappable.** Gemini CLI today, Antigravity 2.0 CLI or anything else tomorrow. Abstract over it.
5. **The dashboard is the proof.** A number you can screenshot is worth more than a claim in a README.

### Component summary

| Dimension | What |
|---|---|
| Brain | Claude Code (plans, reviews, decides) |
| Hands | Gemini CLI `--yolo` (1M context, `@dir/` analysis, session resume) |
| Body | DesktopCommanderMCP + nazir-tools Python MCP (18 tools) |
| Memory | Filesystem checkpoints + SQLite metrics (Phase 6) |
| Visibility | Terminal dashboard (Phase 7) |
| Remote | Tailscale + FastAPI (optional, Phase 10) |
| Security | AppArmor + validate_path + blocklist + Gemini policy TOML |
| Persistence | systemd `--user` services + heartbeat daemon |

---

## 2. What We Learned

Five rounds of research. These constraints are load-bearing — don't revisit them without a specific new signal.

### 2.1 Dead ends (and why)

| Abandoned | Why |
|---|---|
| GUI automation (gnome-desktop-mcp, pyautogui, xdotool) | Wayland blocks all of it on GNOME 42 |
| Newton AT-SPI2 | Requires GNOME 46+ |
| OpenClaw as gateway | CVE-2026-25253 RCE, $300+/month, Google mass-banned users who routed via it |
| Railway relay hosting | Free tier killed in 2026 |
| WebSocket for relay | SSE more reliable, auto-reconnects |
| CodeConductor | Supply chain attack ("Clawjacked") 2026 |
| AionUi | 3 active critical bugs |
| Antigravity in daemon loops | httpx incompatibility + Google ToS → account ban (confirmed real event) |
| GEMINI.md separate context file | "Context Hell" |
| Multiple API keys for more quota | Rate limits are per-project, not per-key |
| Heroku SSE relay | Replaced by Tailscale — simpler, free, encrypted, no cold starts |
| OSS grant (Anthropic) | Requires 5,000+ GitHub stars. Grant = personal Claude Max subscription, NOT API access for daemons. Cannot fund automated pipelines. |
| Always-on autonomous daemon | Claude Pro economics don't work at scale without the grant. Moved to optional. |
| `/stats model` as quota check | Not a valid Gemini CLI slash command. Use stats block from regular call responses. |

### 2.2 What works (probe-verified 2026-05-29, gemini-cli v0.41.2)

| Chosen | Why |
|---|---|
| Gemini CLI as execution backend | Official, `--yolo`, 1M context, session resume works headless |
| `session_id` in JSON stdout | GitHub issue #14435 resolved in v0.41.2 — read directly, no filesystem scraping |
| `GEMINI_API_KEY` env var | Correct var for daemon/headless auth (not `GOOGLE_API_KEY`) |
| `--allowed-mcp-server-names none` | Disables MCP loading in subprocesses — cuts cold-start from 58s to 10s |
| Exit code 41 = auth failure | Confirmed; JSON error body also contains `error.code: 41` |
| `--resume <uuid>` headless | Full session memory confirmed (planted a secret, retrieved it verbatim) |
| `contextFileName: "CLAUDE.md"` | Gemini reads project context automatically |
| Gemini policy TOML | Real, tested, allowlist approach recommended |
| systemctl `--user` services | No sudo required, survive logout with `loginctl enable-linger` |
| Task-loop wrapper (not one-shot) | `claude -p` exits 0 on success — must loop externally |
| AppArmor named profile | Named `nazir-desktop-cmd`, not `/usr/bin/node` (too broad) |
| Tailscale for remote access | Free personal, encrypted, no auth complexity, always-on |
| Claude Code PreCompact + Stop hooks | Fire `wrapup.py` automatically — context amnesia structurally solved |
| Antigravity 2.0 CLI (I/O May 2026) | Official CLI launched, automation-blessed. Third-party proxies still ban risk. |

---

## 3. System Architecture

### 3.1 The Delegation Model

```
You (describe a task)
        ↓
Claude Code — BRAIN
  Plans, reasons, reviews, decides.
  Never reads raw codebases itself.
        ↓
  Delegates heavy work via gemini_runner.py
        ↓
Gemini CLI --yolo — HANDS
  @dir/ file ingestion (1M context)
  Session resume across calls
  Returns condensed summary to Claude
        ↓
nazir-tools MCP + DesktopCommanderMCP — BODY
  Shell, git, search, file ops
  All path-validated against PROJECT_ROOT
        ↓
Your filesystem
```

The key innovation: Claude's context window stays clean for reasoning. Gemini handles the token-heavy work at a fraction of the cost.

### 3.2 Component Map

| Component | Role | Notes |
|---|---|---|
| Claude Code CLI | Orchestrator brain | `--dangerously-skip-permissions` in daemon mode |
| Gemini CLI | Execution backend | `--yolo`, `--resume`, `GEMINI_API_KEY`, `--allowed-mcp-server-names none` |
| DesktopCommanderMCP v0.2.41 | Terminal, file ops | Stdio transport, AppArmor hardened |
| nazir-tools (Python MCP) | 18 project-specific tools | Path validation, blocklist enforced |
| heartbeat daemon | Cognitive loop detection | 5-min stale → git stash → RECOVERY MODE → restart |
| systemd `--user` services | Persistence | `claude-agent` + `heartbeat`, linger enabled |
| wrapup/catchup | Context management | PreCompact + Stop hooks auto-fire wrapup |
| metrics engine (Phase 6) | Cost tracking | SQLite, real $ savings per delegation |
| dashboard (Phase 7) | Observability | Textual TUI, live token meter |
| Tailscale + FastAPI (Phase 10) | Remote access | Optional, localhost on tailnet only |

### 3.3 gemini_runner — How delegation actually works

```python
# Every Gemini subprocess call:
# 1. --allowed-mcp-server-names none  (no MCP loading = 10s not 60s)
# 2. --resume <uuid>  if session exists (auto via ACTIVE_SESSIONS)
# 3. JSON response: {session_id, response, stats}
# 4. session_id captured for next --resume call
# 5. stats block → metrics engine (token counts, latency)

result = run_gemini(
    "@src/ @tests/ Find all API endpoints and their dependencies",
    task_name="api-analysis"          # auto-resumes on subsequent calls
)
# Claude uses the condensed summary — never reads raw files itself
```

### 3.4 Context amnesia — permanently solved (Phase 5)

```
Claude Code context fills → PreCompact hook fires
        ↓
wrapup.py writes memory/last_checkpoint.md
        ↓
Archives to memory/checkpoints/TIMESTAMP.md
        ↓
Persists Gemini session UUIDs to gemini_sessions.json
        ↓
Context compacts (Claude forgets)
        ↓
New session starts
        ↓
catchup() reads checkpoint + restores session UUIDs
        ↓
Agent resumes from exactly where it stopped
```

### 3.5 Agent Loop (current, Phases 0–5 complete)

```
1. Task arrives → memory/current_task.md
2. task-loop wrapper (run-claude.sh) picks it up
3. claude -p "$TASK" --dangerously-skip-permissions
4. Claude reads CLAUDE.md + memory/last_checkpoint.md
5. For each subtask:
   a. Large analysis → gemini_runner (@dir/ syntax)
   b. Code generation → gemini_runner (--resume session)
   c. File/git/shell ops → nazir-tools MCP
   d. Review/decisions → Claude directly
6. Heartbeat touched after each subtask
7. wrapup MCP tool called at 65% context
8. Task complete → git commit → DONE written
9. Loop polls for next task (5s interval)
```

---

## 4. Full Tech Stack

### 4.1 Prerequisites

```bash
# Verified working (probe 2026-05-29)
node --version        # v20.12.2 (via ~/.local)
python3 --version     # 3.10.12
gemini --version      # 0.41.2
claude --version      # 2.1.156
rg --version          # 13.0.0
cgcone --version      # 0.3.5 (npm install -g @cgcone/cli)
```

### 4.2 Environment variables

```bash
# Required — add to ~/.bashrc AND .env
export NAZIR_PROJECT_ROOT="/path/to/nazir"   # single source for all paths
export GEMINI_API_KEY="your-key"             # daemon auth (not GOOGLE_API_KEY)
export GOOGLE_API_KEY="your-key"             # same key, different var name
export GEMINI_TELEMETRY_ENABLED=false        # no code sent to Google
export GEMINI_TELEMETRY_TARGET=local
```

### 4.3 Gemini CLI settings (~/.gemini/settings.json)

```json
{
  "defaultApprovalMode": "auto_edit",
  "telemetry": { "enabled": false, "target": "local" },
  "contextFileName": "CLAUDE.md"
}
```

Note: Do NOT set both `"yolo": true` and `"defaultApprovalMode": "auto_edit"` — contradictory. Use `--yolo` flag per-call.

### 4.4 Gemini CLI policy TOML (~/.gemini/policies/safe-commands.toml)

```toml
[[rules]]
priority = 100
tool = "run_shell_command"
prefix = "git "
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
prefix = "sudo "
decision = "block"
```

### 4.5 Python dependencies

```bash
pip install mcp gitpython python-dotenv tenacity watchdog notify-py
pip install textual rich          # Phase 7 dashboard
pip install aiosqlite             # Phase 6 metrics
```

### 4.6 MCP servers (both CLIs)

```bash
# Claude Code
claude mcp add desktop-commander -- node ~/.local/lib/node_modules/@wonderwhy-er/desktop-commander/dist/index.js
claude mcp add nazir-tools -- python3 $NAZIR_PROJECT_ROOT/mcp_server/server.py

# Gemini CLI — configured in ~/.gemini/settings.json mcpServers
# (done automatically in Phase 2 setup)
```

---

## 5. Directory Structure

```
nazir/
  orchestrator/
    gemini_runner.py      ← Gemini CLI subprocess manager (sessions, resume, stats)
    quota_monitor.py      ← Parse stats block, should_use_gemini()
    task_queue.py         ← Read/write current_task.md, task log
    metrics.py            ← Phase 6: token accounting, $ savings, SQLite writes
    agents.py             ← Phase 8: planner/coder/reviewer/tester roles

  mcp_server/
    server.py             ← FastMCP server (20 tools after Phase 5)
    config.py             ← PROJECT_ROOT, MAX_OUTPUT_BYTES, TEST_COMMAND
    tools/
      shell.py            ← safe_run_command, ping_heartbeat
      files.py            ← safe_read_file, safe_write_file, list_dir
      git.py              ← status, diff, log, commit, add, stash
      search.py           ← search_in_files (rg), find_files
      code.py             ← run_python, run_tests, lint_file

  heartbeat/
    daemon.py             ← 5-min stale detection, 3-strike recovery
    rollback.py           ← git stash (tracked files only), recovery task writer
    notify.py             ← gdbus GNOME notifications + notifypy fallback

  memory/
    wrapup.py             ← Checkpoint writer (hook-callable + MCP tool)
    catchup.py            ← Checkpoint restore + session UUID reload
    updater.py            ← CLAUDE.md section updater
    last_checkpoint.md    ← Current task state (always up to date)
    current_task.md       ← What to do now (task-loop reads this)
    gemini_sessions.json  ← Active session UUIDs (persisted across restarts)
    metrics.db            ← Phase 6: SQLite token/cost log
    checkpoints/          ← Archived checkpoint history
    task_log.jsonl        ← Task completion history

  dashboard/              ← Phase 7
    app.py                ← Textual TUI: task · token meter · $ saved · history
    widgets/              ← Reusable panels
    export.py             ← Static HTML export for README

  security/
    apparmor/
      nazir-desktop-cmd   ← Named AppArmor profile (not /usr/bin/node)
    validate_path.py      ← PROJECT_ROOT enforcement, symlink-safe
    blocklist.py          ← Blocks rm -rf, all sudo, fork bombs

  systemd/
    claude-agent.service  ← systemd --user unit
    heartbeat.service     ← systemd --user unit
    run-claude.sh         ← Task-loop wrapper (not one-shot)

  .claude/
    settings.json         ← PreCompact + Stop hooks → wrapup.py

  CLAUDE.md.example       ← Sanitised template for contributors
  CLAUDE.md               ← Agent context (gitignored — machine-specific paths)
  Nazir_PRD_v4.md         ← This document (single source of truth)
  probe_phase0_5.py       ← Assumption verifier (re-run when upgrading tools)
  test_all_phases.py      ← Integration test suite (run on any machine)
  .geminiignore           ← Prevents MemoryDiscovery quota burn
  .env                    ← Real keys (gitignored)
  .env.example            ← Template
  requirements.txt
  README.md
  .gitignore
```

---

## 6. Build Phases 0–10

**Rule:** build one phase at a time, pass the test before moving on.

---

### Phase 0 — Foundation ✅ COMPLETE

Repo initialized. Gemini CLI confirmed headless `--yolo` with API key auth. `.geminiignore` in place.

---

### Phase 0.5 — Assumption Probe ✅ COMPLETE

`probe_phase0_5.py` ran. Key findings (gemini-cli v0.41.2, 2026-05-29):
- `session_id` in JSON stdout: **confirmed** (issue #14435 resolved)
- `--resume` headless session memory: **confirmed**
- Exit code 41 = auth failure: **confirmed**
- Correct auth var: `GEMINI_API_KEY` not `GOOGLE_API_KEY`
- `--yolo` init time: ~10s (not 30s — probe had wrong timeout)
- Antigravity CLI = Electron IDE app, not headless CLI
- `claude -p` headless: **stable** on this machine (no SIGTERM bug)

---

### Phase 1 — Hardened DesktopCommanderMCP ✅ COMPLETE

- DCM v0.2.41 installed globally (`~/.local/lib/node_modules/`)
- Puppeteer CJS shim applied (md-to-pdf ESM conflict — PDF tools disabled, core works)
- AppArmor named profile `nazir-desktop-cmd` in enforce mode
- Connected: Claude Code (stdio) + Gemini CLI (settings.json mcpServers)
- MCP handshake verified

**Test result:** DCM `✓ Connected`, AppArmor installed, handshake responds with `desktop-commander v0.2.41`.

---

### Phase 2 — Custom Python MCP Server ✅ COMPLETE

18 tools across shell, files, git, search, code, memory (Phase 5 adds 3 more).

Security: `validate_path.py` (PROJECT_ROOT enforcement, symlink-safe) + `blocklist.py` (blocks all `sudo`, `rm -rf`, fork bombs).

**Test result:** 18/18 security + tool tests pass.

---

### Phase 3 — Gemini CLI Orchestration ✅ COMPLETE

- `gemini_runner.py`: direct JSON `session_id` read, 180s timeout, `--allowed-mcp-server-names none` (10s vs 60s cold start)
- `quota_monitor.py`: parse stats block, save to `last_gemini_stats.json`
- `task_queue.py`: write/read/mark-done cycle, PAUSE/DONE markers

**Test result:** 8/8 tests pass including live Gemini call + session memory verified.

---

### Phase 4 — Heartbeat Daemon + systemd ✅ COMPLETE

- Task-loop wrapper `run-claude.sh` (loops on `current_task.md`, not one-shot)
- `heartbeat/daemon.py`: 5-min timeout, 3-strike recovery, `systemctl --user restart`
- `systemd/claude-agent.service` + `heartbeat.service` as `--user` services
- `loginctl enable-linger` active (survive logout)

**Test result:** Live verification — heartbeat detected 323s stale heartbeat, stashed work, wrote RECOVERY MODE task, restarted `claude-agent.service`.

**Bug found + fixed:** `--include-untracked` in rollback stashed uncommitted new files → conflict on pop → 203/EXEC on restart. Fixed to stash tracked files only.

---

### Phase 5 — Context Management ✅ COMPLETE

- `memory/wrapup.py`: writes checkpoint + archives + persists Gemini session UUIDs
- `memory/catchup.py`: restores checkpoint + re-injects session UUIDs into `ACTIVE_SESSIONS`
- `memory/updater.py`: regex-based CLAUDE.md section updater
- 3 new MCP tools: `wrapup`, `catchup`, `update_claude_md`
- Claude Code hooks: `PreCompact` + `Stop` → `wrapup.py` (automatic, no agent action needed)

**Test result:** 16/16 pass including full wrapup→catchup round-trip with Gemini session persistence.

---

### Phase 6 — Metrics & Cost Engine

**Goal:** Make the value proposition measurable. Every Gemini delegation returns a `stats` block with token counts. Capture it, attribute cost, expose it.

**Deliverables:**

```python
# orchestrator/metrics.py
# Called automatically inside run_gemini() after every successful call

def record_delegation(
    task_name: str,
    gemini_stats: dict,       # raw stats block from Gemini JSON response
    claude_tokens_avoided: int,  # estimated Claude tokens this would have cost
    latency_ms: int,
) -> None:
    """Append one row to memory/metrics.db."""

def cost_report(period: str = "week") -> dict:
    """
    Returns:
      gemini_tokens, claude_tokens_avoided, dollars_saved,
      delegation_count, top_tasks
    """

def dollars_saved(claude_tokens: int) -> float:
    """Counterfactual cost: what Claude Pro would charge per million tokens."""
    CLAUDE_OPUS_PER_MTOK = 15.0   # $/MTok input (update if pricing changes)
    return (claude_tokens / 1_000_000) * CLAUDE_OPUS_PER_MTOK
```

**MCP tool added to server.py:**
```python
@mcp.tool()
def cost_report(period: str = "week") -> str:
    """Show token savings and estimated dollar cost avoided by Gemini delegation."""
```

**SQLite schema:**
```sql
CREATE TABLE delegations (
    id          INTEGER PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    task_name   TEXT,
    gemini_model TEXT,
    gemini_tokens INTEGER,
    claude_est_tokens INTEGER,
    dollars_saved REAL,
    latency_ms  INTEGER
);
```

**Integration:** `gemini_runner.py` calls `metrics.record_delegation()` after every successful `run_gemini()` call. Zero overhead to existing code.

**Test:** run 3 delegations, `cost_report()` returns non-zero `dollars_saved`, `memory/metrics.db` has 3 rows.

---

### Phase 7 — Observability Dashboard

**Goal:** The hero artifact. A screenshot-worthy terminal dashboard showing what Nazir is doing and what it's saving.

**Tech:** `textual` (Python TUI framework). Runs in terminal, screenshots beautifully, exportable.

**Layout:**
```
┌─ Nazir ───────────────────────────────────────────────────────────────────┐
│  ⬤ heartbeat: 12s ago   claude-agent: active   gemini sessions: 3 active  │
├─ Active Task ──────────────────────────────────────────────┬─ $ Saved ────┤
│  Analyzing API endpoints in @src/                          │  This week   │
│  Step 3/5: generating endpoint map                         │  $4.21       │
│  [████████████░░░░░░░░░░░░] 47%                            │  Lifetime    │
├─ Token Meter (this task) ──────────────────────────────────│  $18.43      │
│  Claude:  2,840 tokens  (decisions + review)               │              │
│  Gemini: 48,200 tokens  (analysis + generation)            ├─ Sessions ───┤
│  Delegation ratio: 94%                                     │  api-analysis│
├─ Recent Tasks ─────────────────────────────────────────────│  codegen-auth│
│  ✓ write user auth module          2m ago   $0.34 saved    │  test-runner │
│  ✓ analyze legacy db schema        18m ago  $1.12 saved    │              │
│  ✓ generate test suite             1h ago   $0.89 saved    └──────────────┤
│  ✗ fix websocket handler           2h ago   interrupted                   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Deliverables:**
- `dashboard/app.py` — main Textual app
- `dashboard/widgets/` — task panel, token meter, cost panel, session list
- `nazir dashboard` — runnable directly as `python3 dashboard/app.py`
- Live refresh: reads `memory/metrics.db` + `task_log.jsonl` + `/tmp/nazir-heartbeat` every 2s

**Test:** dashboard renders while a task runs; `$ Saved` counter increments after each delegation.

---

### Phase 8 — Specialized Subagents

**Goal:** Replace the single generalist loop with a small team of roles. Better output quality + more impressive architecture.

**Roles:**

| Agent | Model | Responsibility |
|---|---|---|
| planner | Claude (fast) | Breaks task into steps with acceptance criteria |
| coder | Gemini CLI | Writes the code (bulk generation, 1M context) |
| reviewer | Claude (careful) | Reviews diff before commit, sends back if needed |
| tester | nazir-tools | Runs test suite, feeds stderr back to coder |

**Orchestration loop:**
```
plan → [code → test]* → review → commit
              ↑____________|
           (on test failure, max 3 iterations)
```

**Deliverables:**
- `orchestrator/agents.py` — role definitions and orchestration loop
- Leverage Claude Code native subagents where available (don't reinvent)
- `mcp_server/server.py`: `run_agent(role, task)` tool added

**Test:** give it "add a `--dry-run` flag to safe_run_command" — confirm plan → code → tests pass → reviewed diff → committed, all without intervention.

---

### Phase 9 — First Real Mission

**Goal:** Prove Nazir does real work on a real project. This is the most important phase — nothing before it counts until this passes.

**The mission:**
- Pick one genuine, self-contained feature/task in a project you care about
- Hand it to Nazir end-to-end through the Phase 8 subagent loop
- Do not help it unless it's truly stuck

**Document everything in `docs/mission-01.md`:**
- Task description and acceptance criteria
- What Nazir did (git log tells this story)
- What it needed help with (honest)
- Token usage and $ saved (metrics.db)
- What broke and why

**Test:** the feature ships, tests pass, the git history is clean, and the failure log is honest.

**Why this matters for the portfolio:** the failure log is often the most impressive part. Showing you know what your system *can't* do, and designing for it, is senior engineering.

---

### Phase 10 — Showcase & Polish

**Goal:** The 90-second impression. A stranger should understand, believe, and be impressed within 90 seconds of finding the repo.

**Deliverables:**

**README overhaul:**
- `Results` section with real numbers from Phase 9 (not claims — measurements)
- Architecture diagram (the brain/hands/body model, rendered as SVG)
- Dashboard screenshot or demo GIF (asciinema)
- "Quick start in 5 minutes" that actually works

**GitHub Actions CI:**
```yaml
# .github/workflows/ci.yml
- run: python3 test_all_phases.py
```
Green badge in README = proof the stack is always healthy.

**Container isolation (Phase 7 hardening goal):**
```bash
# Replace AppArmor named-profile approach with:
podman run --rm \
  -v $NAZIR_PROJECT_ROOT:/workspace:z \
  --network none \
  node:20-slim \
  node /workspace/node_modules/.bin/desktop-commander
```
Cleaner blast radius than the AppArmor profile that attaches to all node processes.

**Tailscale remote (optional):**
```python
# relay/main.py — listens on Tailscale IP only, not 0.0.0.0
TAILSCALE_IP = subprocess.check_output(["tailscale", "ip", "-4"]).decode().strip()
uvicorn.run(app, host=TAILSCALE_IP, port=8765)
```

**Test:** a stranger can read the README, understand what Nazir is, see proof it works, and clone + run it in under 10 minutes.

---

## 7. Context Management

### Three-layer memory model

```
Layer 1: Context window (ephemeral — RAM)
  → Claude's active reasoning
  → Fires PreCompact hook at ~70% → wrapup.py saves checkpoint
  → Never rely on this for architectural state

Layer 2: Filesystem (persistent — SSD)
  → memory/last_checkpoint.md     current task state
  → memory/checkpoints/           full session archive (timestamped)
  → memory/gemini_sessions.json   active session UUIDs (survive restarts)
  → memory/metrics.db             token/cost history (Phase 6)
  → memory/task_log.jsonl         task completion history
  → CLAUDE.md                     project knowledge base (gitignored, local)

Layer 3: Git history (permanent — backup)
  → every completed task = one commit
  → heartbeat daemon stashes partial work before recovery
  → full audit trail of every agent action
```

### Session UUID lifecycle

```
run_gemini(prompt, task_name="feature-x")
  → Gemini responds with {session_id, response, stats}
  → ACTIVE_SESSIONS["feature-x"] = session_id
  → stats → metrics.record_delegation()

run_gemini(prompt, task_name="feature-x")  # follow-up
  → cmd += ["--resume", ACTIVE_SESSIONS["feature-x"]]
  → Gemini has full context of all prior calls

wrapup() called (hook or explicit)
  → ACTIVE_SESSIONS written to gemini_sessions.json
  → checkpoint written to last_checkpoint.md

New session starts
  → catchup() reads gemini_sessions.json
  → ACTIVE_SESSIONS restored
  → Gemini --resume works as if session never ended
```

---

## 8. systemd Deployment

### Setup (one-time)

```bash
mkdir -p ~/.config/systemd/user/ logs memory/checkpoints
cp systemd/claude-agent.service ~/.config/systemd/user/
cp systemd/heartbeat.service ~/.config/systemd/user/
chmod +x systemd/run-claude.sh
systemctl --user daemon-reload
systemctl --user enable claude-agent.service heartbeat.service
systemctl --user start heartbeat.service
loginctl enable-linger $USER
```

### Monitoring

```bash
journalctl --user -u claude-agent.service -f    # live agent log
journalctl --user -u heartbeat.service -f       # live heartbeat log
systemctl --user status heartbeat.service       # quick status
tail -f logs/agent.log                          # task output
tail -f logs/heartbeat.log                      # recovery events
```

### Send a task

```bash
echo "Your task description here" > memory/current_task.md
# agent picks it up within 5 seconds
tail -f logs/agent.log   # watch it work
```

---

## 9. Security Model

### Nine layers

```
1. validate_path.py       — PROJECT_ROOT enforcement, symlink-safe resolve
2. blocklist.py           — blocks rm -rf, all sudo, fork bombs, disk wipes
3. AppArmor named profile — OS-level for Node process (not /usr/bin/node)
4. Gemini CLI policy TOML — allowlist safe commands, block curl/wget/sudo
5. GEMINI_TELEMETRY=false — no code exfiltration to Google
6. .geminiignore          — prevents MemoryDiscovery quota burn on startup
7. Heartbeat daemon       — kills and restarts a looping agent
8. Git history            — every task = commit, rollback always available
9. Pre-commit hook        — rejects commits containing API key patterns
```

### Threat model

| Threat | Likelihood | Mitigation |
|---|---|---|
| Prompt injection via malicious file | Medium | Gemini policy TOML blocks curl/wget; Claude validates before acting |
| Agent deletes wrong files | Low-Med | validate_path + AppArmor + blocklist |
| API key in git | Low | pre-commit hook catches `AIza...` + `sk-ant` patterns |
| MCP ecosystem RCE (Apr 2026) | Active | AppArmor profile, stdio transport only |
| Gemini --yolo weaponized | Medium | Policy TOML allowlist + telemetry off |
| Context amnesia mid-task | High | PreCompact hook → wrapup.py (automatic) |
| Cognitive loop burning tokens | Medium | Heartbeat daemon + cost governor (Phase 6) |
| MemoryDiscovery quota burn | High | .geminiignore — MUST exist before first run |
| Antigravity third-party proxy | Confirmed ban | Never use OpenClaw or similar proxies |
| API key in chat session | Happened once | Never select .env while in a chat session |

### AppArmor profile notes

The profile attaches to `/home/ahmeed/.local/bin/node`. Because this is the same binary used by Gemini CLI, the profile must allow `~/.gemini/**` — otherwise Gemini subprocess calls are silently blocked.

Phase 10 replaces this with container isolation (podman), which is the architecturally correct solution. AppArmor binary attachment to shared JIT runtimes is inherently fragile.

---

## 10. Infrastructure & Cost

### Current costs

| Component | Monthly | Notes |
|---|---|---|
| Claude Pro | $20 | Funds the orchestrator brain |
| Gemini CLI | $0 | Google AI Pro already paying |
| DesktopCommanderMCP | $0 | Open source |
| nazir-tools | $0 | In-repo |
| cgcone (`@cgcone/cli`) | $0 | Open source |
| Tailscale | $0 | Free personal (≤3 devices) |
| GitHub | $0 | Existing account |

**Total new monthly cost: $0**

### Token economics

| Task type | Handler | Why |
|---|---|---|
| Complex reasoning, architecture | Claude | Irreplaceable judgment |
| Codebase analysis (`@dir/`) | Gemini | 1M context, fraction of Claude cost |
| Bulk code generation | Gemini | Speed + cost |
| Terminal ops, git, search | nazir-tools | Free |
| Code review, decisions | Claude | Judgment > token count |

**Estimated savings vs pure Claude:** 60–75% of tokens, confirmed by Phase 6 metrics (will update with real numbers after Phase 9).

### The OSS grant situation

The Anthropic Claude for Open Source grant requires 5,000+ GitHub stars. Nazir currently has zero. Even if approved, the grant is a personal Claude Max subscription — it explicitly cannot be used for automated pipelines. This is not a funding path for the daemon. Accepted. Moving on.

---

## 11. Milestones & Timeline

| Phase | Deliverable | Status | Key Test |
|---|---|---|---|
| 0 | Foundation | ✅ | Gemini CLI headless --yolo confirmed |
| 0.5 | Assumption probe | ✅ | probe_report.md green, 6 PRD bugs caught |
| 1 | DesktopCommanderMCP | ✅ | DCM Connected, AppArmor enforce |
| 2 | Python MCP server | ✅ | 18/18 security + tool tests |
| 3 | Gemini orchestration | ✅ | 8/8 tests, live call + session resume |
| 4 | Heartbeat + systemd | ✅ | Live recovery: 323s stale → RECOVERY MODE |
| 5 | Context management | ✅ | 16/16 tests, wrapup→catchup round-trip |
| **6** | **Metrics engine** | ✅ | 26/26 tests pass — schema, parse_stats, estimate_savings, 3 delegations, cost_report, cost_governor, MCP tools |
| **7** | **Dashboard** | ✅ | 30/30 tests pass — Textual TUI, data layer, 5 widgets, headless render, SVG+HTML export, 2 MCP tools |
| **8** | **Subagents** | ✅ | 20/20 tests pass — 4 roles, DI orchestrator, pipeline logic (retry/limit/reject), MCP tools |
| **9** | **First real mission** | ✅ | dry_run flag shipped; Gemini correct first try; test spec bug documented; 10/10 tests pass |
| **10** | **Showcase & polish** | ✅ | 11/11 tests pass — README, CI, docs, tests/, remote fixed, heartbeat loop killed |

---

## 12. Failure Modes & Mitigations

| Failure | Impact | Mitigation |
|---|---|---|
| Gemini quota exhausted (429) | Delegation pauses | Phase 6 cost governor detects early; fall back to Claude |
| Session UUID lost | Subagent loses context | gemini_sessions.json persisted in every wrapup |
| claude -p exits 0 silently | Task loop stalls | Task-loop wrapper detects DONE and re-polls |
| systemctl restart from user process | Recovery fails | Uses `systemctl --user` (user can manage user services) |
| AppArmor confines Gemini CLI | Gemini subprocess silently fails | Profile allows ~/.gemini/**; confirmed in Phase 1 tests |
| Puppeteer ESM/CJS crash (DCM) | DCM won't start | CJS shim in place; PDF tools disabled, core works |
| rollback --include-untracked | Stashes uncommitted new files → conflict → 203/EXEC | Fixed: stash tracked files only |
| Context amnesia mid-task | Agent loses context | PreCompact + Stop hooks auto-fire wrapup.py |
| API key selected in IDE during chat | Key visible in conversation | Rotate immediately at aistudio.google.com |
| Heartbeat false alarm | Unnecessary recovery | 5-min timeout, 3 strikes, then PAUSE |
| Task-loop picks up RECOVERY task | Agent confused | Recovery task begins with explicit "RECOVERY MODE" header |

---

## 13. Open Questions

| Question | Status | Decision by |
|---|---|---|
| Claude cost per token for counterfactual? | Use published rate, note date | Phase 6 |
| Textual vs rich for dashboard? | Textual — more powerful, better layout | Phase 7 |
| Native subagents vs orchestrator/agents.py? | Try native first, wrap if needed | Phase 8 |
| What is the first real mission task? | Decide when Phase 8 is done | Phase 9 |
| Container (podman) vs AppArmor long-term? | Container — better isolation, less fragile | Phase 10 |
| Antigravity 2.0 CLI as alternate backend? | Still too new (10 days at PRD writing) | Phase 10 or later |
| Upgrade Pop!_OS to 24.04? | Unlocks GNOME 46, Newton AT-SPI2 | Long term |

---

*Nazir PRD v4.0 — Single source of truth*
*Supersedes: Nazir_PRD.md, Nazir_PRD_v2.md, Nazir_PRD_v3.md, ROADMAP.md*
*Pop!_OS 22.04 · GNOME 42 · Claude Code + Gemini CLI · May 2026*
*Phases 0–5 complete. Phases 6–10: metrics → dashboard → subagents → mission → showcase*
