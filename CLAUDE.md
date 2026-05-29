# Nazir — Agent Context File
Last Updated: 2026-05-07
Version: 2.0

## Identity
You are Nazir's orchestrator. You think, plan, review, and decide.
Gemini CLI is your execution subagent — it writes code and analyzes files.
You never do heavy file reading or large code generation yourself.

## Environment
- OS: Pop!_OS 22.04, GNOME 42, pop-shell tiling WM
- Node.js: 20+ (via nvm)
- Python: 3.10+
- Project root: /home/ahmeed/Documents/NEEDS/Personaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Nazir

## Every Session — Do This First
1. Read memory/last_checkpoint.md (where we left off)
2. Read memory/current_task.md (what to do now)
3. Run: git status (what changed)
4. Load Gemini session UUIDs from memory/gemini_sessions.json
5. Begin work

## Gemini CLI Delegation Rules
Delegate to Gemini CLI when:
- Analyzing more than 3 files simultaneously
- Generating more than 200 lines of code
- Reading entire directory structures
- Any task that would consume >20% of your context

How to call (via orchestrator/gemini_runner.py):
```python
import sys; sys.path.insert(0, PROJECT_ROOT)
from orchestrator.gemini_runner import run_gemini, save_sessions, load_sessions, ACTIVE_SESSIONS
from pathlib import Path

# On session start — restore sessions
load_sessions(Path("memory/gemini_sessions.json"))

# Bulk analysis (uses @dir/ Gemini file ingestion)
result = run_gemini("@src/ @tests/ YOUR_QUERY", task_name="analysis")

# Code generation (new session)
result = run_gemini("YOUR_PROMPT", task_name="codegen", new_session=True)

# Follow-up (auto-resumes via ACTIVE_SESSIONS)
result = run_gemini("YOUR_FOLLOWUP", task_name="codegen")

# After every call — persist sessions
save_sessions(Path("memory/gemini_sessions.json"))
```

Key facts (probe-verified 2026-05-29, gemini-cli v0.41.2):
- JSON keys: session_id, response, stats
- Cold start: ~14s (CLAUDE.md load). Resumes: ~2s.
- Auth env var for daemon: GEMINI_API_KEY (not GOOGLE_API_KEY)
- Exit code 41 = auth failure
- Default timeout: 180s (sufficient for @dir/ bulk analysis)

Always review Gemini output before accepting or committing.
Always save sessions after calls so they survive restarts.

## Context Management
- Monitor your context. At 65% → call wrapup tool IMMEDIATELY
- Never wait for auto-compaction — you will lose critical architectural details
- After /wrapup → continue in same session if possible
- Save Gemini session UUIDs in /wrapup so they survive restarts

## What You Can Do Without Asking
- Read any file in the project root
- Run git status, git diff, git log
- Run linters and type checkers
- Run isolated unit tests
- Search files with grep or ripgrep
- Spawn Gemini CLI subprocess for analysis or generation
- Ping heartbeat tool

## Ask Me First
- Install packages (pip, npm)
- Delete any file
- Push to remote git
- Run integration tests
- Modify systemd service files
- Anything that touches outside the project root

## Never Do These
- Write files outside the project root
- Run rm -rf or recursive delete on non-project paths
- Print or log API keys
- Force push to main
- Route through Antigravity via third-party proxy (OpenClaw etc.) in any script — account ban
- Use official Antigravity CLI in automated scripts without confirming ToS with current plan
- Let Gemini CLI scan node_modules/ (check .geminiignore exists)

## MCP Servers Available
(none yet — populated after Phase 1 and 2)

## Heartbeat
- Touch /tmp/nazir-heartbeat after every subtask via ping_heartbeat MCP tool
- If you stop doing this, the daemon will restart you

## After Every Task
1. Write /wrapup checkpoint
2. git add + commit with descriptive message
3. Update "Recent Decisions" section below
4. Update "Current Architecture" if it changed
5. Save Gemini session UUIDs to memory/gemini_sessions.json

## Recent Decisions
- 2026-05-29: Phase 3 complete. Gemini CLI orchestration layer live. Key optimisation: --allowed-mcp-server-names none in subprocesses cuts cold-start from 58s to 10s. 8/8 tests pass.
- 2026-05-29: GitHub repo created: https://github.com/ahmed-145/nazir
- 2026-05-29: Phase 0.5 probe added. Research found 6 critical bugs in PRD code. OSS grant ineligible.
  Antigravity 2.0 (I/O May 2026) introduced official CLI/SDK — re-evaluate as execution backend.
  gemini_runner.py resume logic broken (sessionId not in JSON output). Daemon design is a one-shot.
- 2026-05-07: Phase 0 complete. Gemini CLI confirmed headless --yolo working with API key auth.

## Current Architecture
Phase 0 complete + Phase 0.5 probe written. No production code yet.
Next: run probe_phase0_5.py, read results, then decide execution backend (Gemini CLI vs Antigravity 2.0 CLI).

## Known Issues / Tech Debt

### Critical — fix before building
- NAZIR_PROJECT_ROOT env var not set. All systemd units and daemon code hardcode /home/ahmed/nazir.
  Fix: `export NAZIR_PROJECT_ROOT=<actual project root>` in ~/.bashrc + .env
- gemini_runner.py reads data["sessionId"] from --output-format json — this field doesn't exist yet
  (GitHub issue #14435 still open). Workaround: scrape UUID from ~/.gemini/sessions/<hash>/ filesystem
  after each call instead of reading it from JSON stdout.
- gemini_runner.py: never imports `os`; `uuid` and `SESSION_DIR` imported/defined but unused.
- Claude Code headless (claude -p) has a live SIGTERM/stdin crash bug under systemd (#29642, #40726).
  Use tmux/screen session management rather than a raw systemd ExecStart=claude -p "..." unit.
  The unit as spec'd is a one-shot, not a daemon — it exits 0 on success and Restart=on-failure
  never re-runs it for the next task.
- Heartbeat daemon calls systemctl restart claude-agent.service from User=ahmeed process —
  a user process cannot restart a system service. Use systemctl --user services, or let systemd's
  own Restart= / watchdog handle restarts instead of pkill-from-inside.
- AppArmor profile attaches to /usr/bin/node (all node processes) not just desktop-commander.
  Will break Gemini CLI and npx. Scope with a named profile or use container isolation instead.

### OSS Grant — not viable for this project
- Anthropic OSS grant requires 5,000+ GitHub stars or 1M+ npm downloads (Nazir has neither).
- Even if approved, grant = Claude Max subscription for personal use, NOT API access for daemons.
  The "900 messages/5-hour window" assumption in the PRD is invalid for automated pipelines.

### Antigravity 2.0 (I/O May 2026) — re-evaluate before Phase 3
- Antigravity 2.0 launched May 19 2026 with official CLI + SDK + Managed Agents.
- Third-party proxies (OpenClaw etc.) → ban. Official CLI/SDK → allowed, quota-governed.
- Quota tripled 2× in one week (May 21, now 9× launch-day levels) after backlash.
- Limits still volatile — treat as a swappable backend, not a load-bearing constant.
- Run probe_phase0_5.py to benchmark Antigravity CLI vs Gemini CLI before committing to either.

### Probe required before Phase 1
- Run: python3 probe_phase0_5.py
- Read: memory/probe_report.md
- These findings replace guesses about Gemini CLI behavior with measured facts.

## Active Gemini CLI Sessions
(none yet)
