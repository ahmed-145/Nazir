# Nazir — Roadmap

> Phases 0–5 are complete (the platform). Phases 6–10 are the enhancement track,
> reframed around what Nazir is actually *for*: a **token-saving orchestration layer
> for interactive work** + a **portfolio-grade showcase** of multi-LLM agent architecture.

## What changed in direction (2026-05-30)

The original PRD aimed at a 24/7 autonomous daemon. That goal carried two unsolved
problems — Claude Pro quota economics and unattended-write safety — and was also the
least impressive part to show. We're **de-prioritising always-on autonomy** to an
optional toggle and leading instead with:

1. **Measured value** — token/dollar savings from Claude→Gemini delegation, tracked and shown.
2. **Visible polish** — a dashboard you can screenshot, a demo that lands in 90 seconds.
3. **Real usefulness** — something the author actually uses for interactive coding.

---

## Status

| Phase | Title | Status |
|---|---|---|
| 0 | Foundation | ✅ |
| 0.5 | Assumption probe | ✅ |
| 1 | Hardened DesktopCommanderMCP | ✅ |
| 2 | Custom Python MCP server (18 tools) | ✅ |
| 3 | Gemini CLI orchestration | ✅ |
| 4 | Heartbeat daemon + systemd | ✅ |
| 5 | Context management (wrapup/catchup) | ✅ |
| 6 | Metrics & cost engine | ⬜ next |
| 7 | Observability dashboard | ⬜ |
| 8 | Specialized subagents | ⬜ |
| 9 | First real mission | ⬜ |
| 10 | Showcase & polish | ⬜ |
| — | Unattended mode (optional) | ⏸ de-prioritised |

---

## Phase 6 — Metrics & Cost Engine

**Goal:** Make the core value proposition measurable. Every Gemini delegation already
returns a `stats` block (token counts per model). Capture it, attribute cost, persist it.

**Deliverables**
- `orchestrator/metrics.py` — parse the `stats` block from every `run_gemini` call;
  record `{task, timestamp, claude_tokens_est, gemini_tokens, model, latency_ms}`.
- `memory/metrics.db` (SQLite) — append-only metrics table.
- Cost model: estimate what those Gemini tokens *would have cost* on Claude
  (the counterfactual = the savings story). Use published per-token rates.
- `nazir-tools` MCP tool: `cost_report(period)` → "This week: 1.2M tokens delegated
  to Gemini, ~$X saved vs Claude-only."

**Test:** run 3 delegations, confirm metrics.db has 3 rows with non-zero token counts
and a computed savings figure.

**Why first:** every later phase (dashboard, showcase) depends on having real numbers.

---

## Phase 7 — Observability Dashboard

**Goal:** The hero artifact. One screen that shows what Nazir is doing and what it's saving.

**Deliverables**
- `dashboard/` — a `textual` TUI (Python, runs in terminal, screenshots beautifully).
  Panels: active task · live token meter (Claude vs Gemini) · $ saved (cumulative) ·
  recent task history · heartbeat status · active Gemini sessions.
- Reads from `memory/metrics.db`, `memory/task_log.jsonl`, `/tmp/nazir-heartbeat`.
- `nazir dashboard` command (or `python3 dashboard/app.py`).
- Optional: a single-file static HTML export for the README.

**Test:** dashboard renders live data while a task runs; numbers update.

**Why:** this is the thing a viewer sees first. It's also genuinely useful for you.

---

## Phase 8 — Specialized Subagents

**Goal:** Move from one generalist loop to a small team of roles. More impressive,
better output, and shows real agent-orchestration design.

**Deliverables**
- `orchestrator/agents.py` defining roles:
  - **planner** — breaks a task into steps (Claude, cheap, high-judgment)
  - **coder** — writes the code (Gemini for bulk, Claude for tricky)
  - **reviewer** — reviews the diff before commit (Claude)
  - **tester** — runs the test suite, feeds failures back (nazir-tools)
- A simple orchestration loop: plan → code → test → review → commit, with the
  reviewer able to send work back to the coder.
- Leverage Claude Code's native subagents where possible (don't reinvent).

**Test:** give it a small feature request; confirm the plan→code→test→review cycle
runs and produces a reviewed commit.

---

## Phase 9 — First Real Mission

**Goal:** Prove Nazir does real work. Nothing before this counts until this passes.

**Deliverables**
- Pick one small, real, self-contained task (a CLI tool, a script, a small feature
  in an existing repo).
- Run it through the full stack: task → delegation → tests → checkpoint → commit.
- Document what worked, what broke, what needed human intervention.
- A short writeup (`docs/mission-01.md`) — this becomes portfolio content too.

**Test:** the feature ships, tests pass, and the failure/intervention log is honest.

---

## Phase 10 — Showcase & Polish

**Goal:** The 90-second impression for anyone who finds the repo.

**Deliverables**
- Demo GIF/asciinema in README: Nazir delegating a real codebase analysis with the
  live cost counter visible.
- Architecture diagram (the brain/hands/body model, rendered).
- GitHub Actions CI: run `test_all_phases.py` on push, green badge in README.
- Container isolation option (podman) as a cleaner alternative to the AppArmor profile.
- A "Results" section in the README with real numbers from Phase 6.

**Test:** a stranger can understand what Nazir is, see proof it works, and run it.

---

## Known trade-offs we're accepting

- **Not 24/7 autonomous.** Interactive + burst use only. This is a deliberate scope
  cut, not a gap. The daemon stays as an optional toggle.
- **AppArmor profile is functional but brittle** (attaches to the shared node binary).
  Phase 10 offers container isolation as the cleaner long-term answer.
- **Economics unsolved for unattended mode** — intentionally out of scope now.

---

## North-star metric

> **Tokens delegated to Gemini → dollars saved vs Claude-only.**
> If that number is real, visible, and growing, Nazir is succeeding at what it's for.
