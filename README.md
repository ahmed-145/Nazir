# Nazir

> Linux-native autonomous AI agent platform — Claude Code orchestrates, Gemini CLI executes.

Built for Pop!_OS 22.04 / GNOME 42. Works entirely through CLI, APIs, and the filesystem — no GUI automation, no Wayland hacks, no cloud dependency for the core loop.

---

## Architecture

```
You → Claude Code (brain: plans, reviews, decides)
           ↓ delegates bulk work
      Gemini CLI --yolo (hands: 1M-context file analysis, code gen)
           ↓
      DesktopCommanderMCP + nazir-tools MCP (body: terminal, git, search)
           ↓
      Your filesystem
```

**Key insight:** Claude Code's context window is expensive. Nazir routes large file analysis and bulk code generation to Gemini CLI (`@dir/` syntax, 1M token context), keeping Claude's context clean for reasoning and decisions.

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Orchestrator | Claude Code CLI | Plans, reviews, never reads raw codebases |
| Execution | Gemini CLI `--yolo` | 1M context, `@dir/` file ingestion, session resume |
| Terminal/git | DesktopCommanderMCP v0.2.41 | MCP stdio transport, AppArmor hardened |
| Project tools | nazir-tools (Python MCP) | Path-safe shell, git, search, heartbeat |
| Persistence | systemd `--user` services | Survives reboots, no sudo required |
| Recovery | Heartbeat daemon | Detects loops, stashes work, restarts agent |
| Security | AppArmor + validate_path + blocklist | Defense in depth, no single point of failure |
| Sync | cgcone (`@cgcone/cli`) | One command installs MCP on Claude Code + Gemini CLI |

---

## Build Phases

| Phase | Status | What it delivers |
|---|---|---|
| 0 | ✅ Done | Repo, Gemini CLI, `.geminiignore` |
| 0.5 | ✅ Done | Assumption probe — verifies all API behavior before writing code |
| 1 | ✅ Done | DesktopCommanderMCP, AppArmor named profile |
| 2 | ✅ Done | Custom Python MCP server (17 tools) |
| 3 | ✅ Done | Gemini CLI orchestration layer, session persistence |
| 4 | 🔄 In progress | Heartbeat daemon + systemd `--user` services |
| 5 | ⬜ Next | Context management (wrapup/catchup) |
| 6 | ⬜ | Tailscale remote access (optional) |
| 7 | ⬜ | Production hardening |

---

## Quick Start

### Prerequisites

- Pop!_OS / Ubuntu 22.04+ (GNOME 42)
- Python 3.10+
- Node.js 20+ (install via nvm)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Gemini CLI (`npm install -g @google/gemini-cli`)
- A Google AI Pro account with a Gemini API key from [aistudio.google.com](https://aistudio.google.com)

### Setup

```bash
git clone https://github.com/ahmed-145/nazir.git
cd nazir

# Copy and fill in your keys
cp .env.example .env
# Edit .env: set GOOGLE_API_KEY, GEMINI_API_KEY, NAZIR_PROJECT_ROOT

# Copy and customise the agent context file
cp CLAUDE.md.example CLAUDE.md
# Edit CLAUDE.md: update paths to match your machine

# Add NAZIR_PROJECT_ROOT to your shell
echo 'export NAZIR_PROJECT_ROOT="/path/to/nazir"' >> ~/.bashrc
source ~/.bashrc

# Install Python deps
pip install mcp gitpython python-dotenv tenacity watchdog notify-py

# Install MCP sync tool
npm install -g @cgcone/cli

# Run the assumption probe (verifies your environment before building)
python3 probe_phase0_5.py
cat memory/probe_report.md
```

### Verify MCP servers are connected

```bash
claude mcp list
# Should show: desktop-commander ✓ Connected, nazir-tools ✓ Connected
```

### Run the daemon

```bash
# Write a task
echo "Read CLAUDE.md and tell me the current architecture." > memory/current_task.md

# Start services
systemctl --user start heartbeat.service
systemctl --user start claude-agent.service

# Watch the agent work
tail -f logs/agent.log
```

---

## MCP Tools (nazir-tools)

| Tool | Description |
|---|---|
| `run_command` | Shell — PROJECT_ROOT confined, blocklist enforced |
| `heartbeat` | Touch `/tmp/nazir-heartbeat` (daemon watchdog) |
| `read_file` / `write_file` / `list_directory` | Path-validated file ops |
| `status` / `diff` / `log` / `commit` / `stage` / `stash` | Git operations |
| `search` | ripgrep-powered code search |
| `find` | Find files by name pattern |
| `run_script` / `test` / `lint` | Python runner, pytest, ruff |

---

## Security Model

Nine layers, defence in depth:

1. `validate_path.py` — rejects any path outside `PROJECT_ROOT` (symlink-safe)
2. `blocklist.py` — blocks `rm -rf`, all `sudo`, fork bombs, disk wipes
3. AppArmor named profile — OS-level confinement for the Node process
4. Gemini CLI policy TOML — allowlist safe commands, block `curl`/`wget`/`sudo`
5. `GEMINI_TELEMETRY_ENABLED=false` — no code sent to Google
6. `.geminiignore` — prevents Gemini MemoryDiscovery from burning quota on boot
7. Heartbeat daemon — kills and restarts a looping agent
8. Git history — every completed task is a commit; rollback always available
9. Pre-commit hook — rejects commits containing API key patterns

---

## Key Decisions

- **Gemini CLI not Antigravity in automation** — Antigravity's third-party proxy (OpenClaw) got users banned by Google. Gemini CLI is the officially supported automation path.
- **`--allowed-mcp-server-names none`** — disables MCP loading in Gemini subprocess calls, cutting cold-start from ~60s to ~10s.
- **`systemctl --user`** — no sudo required; user services survive logout with `loginctl enable-linger`.
- **`session_id` in JSON** — GitHub issue #14435 resolved in gemini-cli v0.41.2; session UUID read directly from stdout, no filesystem scraping needed.
- **`GEMINI_API_KEY`** (not `GOOGLE_API_KEY`) — correct env var for forcing API key auth in headless/daemon mode.

---

## Research

Four rounds of research, one live verification session (May 2026). See `Nazir_PRD_v3.md` for the full spec including lessons learned, failure modes, and open questions.

---

## License

MIT
