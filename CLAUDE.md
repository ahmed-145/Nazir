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

How to call Gemini CLI:
```bash
# For analysis:
gemini --yolo --output-format json -p "@src/ @tests/ YOUR_QUERY"

# For code generation (new session):
gemini --yolo --output-format json -p "YOUR_GENERATION_PROMPT"

# For follow-up (resume session):
gemini --yolo --resume SESSION_UUID --output-format json -p "YOUR_FOLLOWUP"
```

Always save session UUIDs to memory/gemini_sessions.json after each call.
Always review Gemini output before accepting or committing.

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
- Call Antigravity Manager proxy in automated scripts
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
- 2026-05-07: Phase 0 complete. Gemini CLI confirmed headless --yolo working with API key auth.

## Current Architecture
Phase 0 only. Repo initialized, Gemini CLI configured, policies set.

## Known Issues / Tech Debt
(none yet)

## Active Gemini CLI Sessions
(none yet)
