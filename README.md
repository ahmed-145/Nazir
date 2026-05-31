# Nazir

**A Linux-native AI agent platform that uses Claude as the orchestrator brain and Gemini CLI as the execution hands.**

Routes large file analysis and bulk code generation to Gemini's 1M-context window — sparing Claude's expensive context for reasoning and decisions — and tracks the dollar savings from every delegation in real time.

---

## Results (measured, not claimed)

| Metric | Value |
|--------|-------|
| Gemini delegations | **218** |
| Tokens routed to Gemini | **5,083,231** |
| Estimated dollars saved vs Claude-only | **$7.41** |
| Delegation ratio | **~66% of tokens handled by Gemini** |
| Test suite | **166/166 passing** |
| Real mission shipped | **`dry_run` flag — Gemini correct on first try** |

Numbers are live from `memory/metrics.db` — updated every session.

---

## Architecture

```
You (describe a task)
        ↓
Claude Code ── BRAIN
  Plans, reasons, reviews, decides.
  Never reads raw codebases itself.
        ↓
  Delegates heavy work via gemini_runner.py
        ↓
Gemini CLI --yolo ── HANDS
  @dir/ file ingestion (1M context)
  Session resume across calls
  Returns condensed summary to Claude
        ↓
nazir-tools MCP + DesktopCommanderMCP ── BODY
  Shell, git, search, file ops
  All path-validated against PROJECT_ROOT
        ↓
Your filesystem
```

**The key innovation:** Claude's context window stays clean for reasoning. Gemini handles the token-heavy work at a fraction of the cost. Every delegation is recorded with token counts and estimated dollar savings.

### Component Map

| Component | Role |
|-----------|------|
| Claude Code CLI | Orchestrator brain — plans, reviews, decides |
| Gemini CLI `--yolo` | Execution backend — 1M context, `@dir/` analysis, session resume |
| DesktopCommanderMCP | Terminal, file ops (stdio, AppArmor hardened) |
| nazir-tools (Python MCP) | 20+ project-specific tools, path-validated |
| `orchestrator/agents.py` | 4-role subagent pipeline: planner→coder→tester→reviewer |
| `orchestrator/metrics.py` | SQLite cost engine — tokens and $ per delegation |
| `dashboard/` | Textual TUI — live token meter, $ saved counter, task history |
| Heartbeat daemon | Detects stalled agent, stashes work, triggers recovery |
| systemd `--user` services | Persistence across restarts, survives logout |
| Context hooks | PreCompact + Stop → `wrapup.py` — amnesia structurally solved |

---

## Dashboard

The terminal TUI shows what Nazir is doing and what it's saving, live:

```
┌─ Nazir ──────────────────────────────────────────── 18:43:02 ─┐
│  ⬤ heartbeat: 12s ago   claude-agent: active   sessions: 2    │
├─ Active Task ──────────────────────────────┬─ $ Saved ─────────┤
│  Add dry_run flag to safe_run_command      │  This week        │
│                                            │  $1.73            │
├─ Token Meter — lifetime ───────────────────│  Lifetime         │
│  Claude:  2,541,615 tokens (decisions)     │  $7.41            │
│  Gemini:  5,083,231 tokens (analysis)      │                   │
│  Delegation ratio: 66.6%                   ├─ Sessions ────────┤
├─ Recent Tasks ─────────────────────────────│  warmup           │
│  ✓ dry_run flag shipped     just now $1.73 │  integration-test │
│  ✓ phase 8 subagents        1h ago   $0.28 └───────────────────┤
└────────────────────────────────────────────────────────────────┘
```

Run: `python3 dashboard/app.py`
Export snapshot: `python3 dashboard/app.py --export-html`

---

## Subagent Pipeline

```
plan → [code → test]* → review → commit
              ↑____________|
           (on failure, max 3 iterations)
```

| Agent | Engine | Responsibility |
|-------|--------|----------------|
| Planner | Claude `-p` | Breaks task into steps with acceptance criteria |
| Coder | Gemini CLI | Writes the code (bulk generation, 1M context) |
| Tester | subprocess | Runs test suite, feeds failures back to Coder |
| Reviewer | Claude `-p` | Reviews diff — APPROVED or REVISION_NEEDED |

**Mission 01 result:** Gemini implemented a new feature correctly on the first attempt. Pipeline ran unattended. Human assist: 1 test assertion fix, 2 minutes. See `docs/mission-01.md`.

---

## Quick Start

### Prerequisites

```bash
node --version    # v20+
python3 --version # 3.10+
gemini --version  # 0.41.2+  →  npm install -g @google/gemini-cli
```

### Install

```bash
git clone https://github.com/ahmed-145/Nazir
cd Nazir
pip install mcp gitpython python-dotenv tenacity watchdog textual rich aiosqlite

cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

### Configure

```bash
export GEMINI_API_KEY="your-key-here"
export NAZIR_PROJECT_ROOT="$(pwd)"

# Register MCP servers with Claude Code
claude mcp add desktop-commander -- node \
  ~/.local/lib/node_modules/@wonderwhy-er/desktop-commander/dist/index.js
claude mcp add nazir-tools -- python3 $NAZIR_PROJECT_ROOT/mcp_server/server.py
```

### Run

```bash
# Start services
systemctl --user start claude-agent.service heartbeat.service

# Send a task
echo "Your task here" > memory/current_task.md

# Watch it work
tail -f logs/agent.log

# Open dashboard
python3 dashboard/app.py
```

### Test

```bash
python3 test_all_phases.py
# Expected: 166/166 passing
```

---

## Project Structure

```
Nazir/
  orchestrator/
    gemini_runner.py    ← Gemini CLI subprocess manager (sessions, resume, stats)
    agents.py           ← 4-role subagent pipeline (planner/coder/tester/reviewer)
    metrics.py          ← Token cost engine — SQLite, $ savings per delegation
    quota_monitor.py    ← Gemini usage monitor
    task_queue.py       ← Task read/write/mark-done

  mcp_server/
    server.py           ← FastMCP server (20+ tools)
    tools/              ← shell, files, git, search, code

  dashboard/
    app.py              ← Textual TUI (2s live refresh)
    data.py             ← Data layer (heartbeat, metrics, tasks)
    export.py           ← HTML + SVG snapshot export
    widgets/            ← StatusBar, TaskPanel, CostPanel, TokenMeter, SessionPanel

  heartbeat/
    daemon.py           ← 5-min stale detection, 3-strike recovery
    rollback.py         ← git stash + RECOVERY MODE task writer
    notify.py           ← GNOME desktop notifications

  memory/
    wrapup.py           ← Checkpoint writer (PreCompact + Stop hook)
    catchup.py          ← Checkpoint restore + session UUID reload
    updater.py          ← CLAUDE.md section updater
    metrics.db          ← Live token/cost SQLite database

  security/
    validate_path.py    ← PROJECT_ROOT enforcement, symlink-safe
    blocklist.py        ← Blocks rm -rf, sudo, fork bombs

  systemd/
    claude-agent.service
    heartbeat.service
    run-claude.sh       ← Task-loop wrapper (not one-shot)

  docs/
    mission-01.md       ← Phase 9 real mission report (honest)

  tests/
    mission_01_test.py  ← Phase 9 acceptance tests

  test_all_phases.py    ← Full integration suite (166 tests, Phases 0–10)
  probe_phase0_5.py     ← Assumption verifier (re-run when upgrading tools)
  Nazir_PRD_v4.md       ← Product requirements (single source of truth)
```

---

## Build Phases

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 0 | Foundation — repo, Gemini CLI headless confirmed | ✅ |
| 0.5 | Assumption probe — 6 PRD bugs caught before coding | ✅ |
| 1 | DesktopCommanderMCP + AppArmor | ✅ |
| 2 | Python MCP server — 20 tools, path validation, blocklist | ✅ |
| 3 | Gemini CLI orchestration — sessions, resume, stats | ✅ |
| 4 | Heartbeat daemon + systemd `--user` services | ✅ |
| 5 | Context management — wrapup/catchup hooks, amnesia solved | ✅ |
| 6 | Metrics engine — SQLite, $ savings per delegation | ✅ |
| 7 | Observability dashboard — Textual TUI, SVG/HTML export | ✅ |
| 8 | Specialized subagents — 4-role pipeline, DI orchestrator | ✅ |
| 9 | First real mission — feature shipped, Gemini correct 1st try | ✅ |
| 10 | Showcase & polish — README, CI, tests | ✅ |

---

## Why This Exists

Three problems that motivated this:

**1. Claude's context is expensive.** Reading an entire codebase in Claude burns tokens fast. Gemini CLI has a 1M-token context window at a fraction of the cost. Route the heavy reads there, keep Claude for decisions.

**2. Context amnesia kills long sessions.** Claude forgets mid-task when the context window fills. Nazir's PreCompact/Stop hooks auto-save checkpoints and restore them on next session — structurally solved, not papered over.

**3. Unattended agents are dangerous without guardrails.** An agent that loops forever, makes wrong writes, or loses its place after a crash is worse than no agent. Nazir has a heartbeat daemon, git-stash rollback, and RECOVERY MODE.

---

## Security

Nine overlapping controls — none sufficient alone:

1. `validate_path.py` — PROJECT_ROOT enforcement, symlink-safe resolve
2. `blocklist.py` — blocks `rm -rf`, all `sudo`, fork bombs, disk wipes
3. AppArmor named profile — OS-level for Node process (not `/usr/bin/node`)
4. Gemini CLI policy TOML — allowlist safe commands, block `curl`/`wget`/`sudo`
5. `GEMINI_TELEMETRY=false` — no code exfiltration to Google
6. `.geminiignore` — prevents MemoryDiscovery quota burn on startup
7. Heartbeat daemon — kills and restarts a looping agent
8. Git history — every task = commit, rollback always available
9. Pre-commit hook — rejects commits containing API key patterns

---

## What It Can't Do (Honest)

- **GUI automation** — GNOME 42 on Wayland blocks all of it
- **Truly autonomous daemon** — Claude Pro economics require human-in-loop for long runs; daemon mode exists as an optional toggle
- **Self-correct a bad test spec** — Mission 01 proved this: if the acceptance test is wrong, the pipeline can't fix it (took 2 min of human assist)
- **Container isolation** — planned (podman), deferred — not installed on this machine
- **Remote access** — planned (Tailscale), deferred — not installed on this machine

---

## License

MIT

---

*Pop!_OS 22.04 · GNOME 42 · Claude Code 2.1.157 · Gemini CLI 0.41.2*
*166/166 tests · $7.41 saved · 5,083,231 tokens delegated to Gemini*
