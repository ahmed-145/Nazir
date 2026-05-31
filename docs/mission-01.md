# Mission 01 — Add `dry_run` to `safe_run_command`

**Date:** 2026-05-31
**Phase:** 9 — First Real Mission
**Status:** ✅ COMPLETE (with one human assist — see failure log)

---

## Task

Add a `dry_run` parameter to `safe_run_command` in `mcp_server/tools/shell.py`.

**Exact specification:**
- New signature: `safe_run_command(cmd, cwd=None, timeout=30, dry_run=False)`
- When `dry_run=True`: run blocklist check, then return `"DRY_RUN: would execute: <cmd>"` without executing
- When `dry_run=False` (default): existing behavior unchanged, fully backward compatible
- MCP tool `run_command` in `server.py` must also expose the parameter

## Acceptance Criteria

All 7 tests in `tests/mission_01_test.py` pass:
1. `safe_run_command` importable ✅
2. Signature contains `dry_run` parameter ✅
3. `dry_run=True` returns `"DRY_RUN:"` prefix, does NOT execute ✅
4. `dry_run=False` executes normally ✅
5. Default (no arg) is backward compatible ✅
6. Blocklist still enforced when `dry_run=True` ✅
7. `dry_run` default value is `False` ✅

## Pre-Flight Baseline

| Metric | Value |
|--------|-------|
| Delegations to date | 197 |
| Dollars saved to date | $5.2039 |
| Full test suite | 156/156 passing |
| mission_01_test.py | 2/7 passing (feature not implemented) |

## Pipeline Configuration

```python
SubagentOrchestrator(test_command="python3 tests/mission_01_test.py")
.run_pipeline(task, dry_run=False, max_iterations=3)
```

Test command was scoped to `mission_01_test.py` (not full suite) — avoids
the ~60s live Gemini call in Phase 3 tests per iteration.

---

## What Nazir Did

### Planner (Claude -p)

Produced a clean 6-step plan in structured JSON:

1. Add `dry_run: bool = False` parameter to `safe_run_command` signature
2. Call `check_command(cmd)` unconditionally (blocklist before dry_run branch)
3. If `dry_run is True`, return `'DRY_RUN: would execute: ' + cmd` immediately
4. Leave the existing `dry_run=False` path completely unchanged
5. Add `dry_run: bool = False` to `run_command` MCP tool in `server.py`
6. Pass `dry_run=dry_run` through to `safe_run_command` inside that handler

Assessment: **perfect plan.** All 6 steps were necessary and sufficient.

### Iteration 1 — Coder (Gemini CLI)

Gemini implemented the feature **correctly**:

```python
def safe_run_command(cmd: str, cwd: str = None, timeout: int = 30, dry_run: bool = False) -> str:
    check_command(cmd)
    if dry_run:
        return f"DRY_RUN: would execute: {cmd}"
    # ... existing path unchanged
```

Also updated `server.py` MCP tool correctly:
```python
def run_command(cmd: str, cwd: str = None, timeout: int = 30, dry_run: bool = False) -> str:
    return safe_run_command(cmd, cwd, timeout, dry_run)
```

**Test result: 6/7 passing.** The one failing test:

```
FAIL  dry_run=True behavior wrong
      command was actually executed: 'DRY_RUN: would execute: echo SHOULD_NOT_APPEAR'
```

### Why That Test Failed

The test checked `"SHOULD_NOT_APPEAR" not in out`. The dry_run output was
`"DRY_RUN: would execute: echo SHOULD_NOT_APPEAR"` — which **does** contain
"SHOULD_NOT_APPEAR" as part of the command text. The assertion was ambiguous:
it couldn't distinguish "the string appears in the dry_run description"
from "the string appeared because the command was executed."

**This was a test specification bug, not a Gemini implementation bug.**

### Iterations 2 and 3

Gemini CLI exited non-zero (coder_ok=False) on both retry attempts — likely
quota/rate limit after the long iteration 1. The feedback loop provided the
test output to Gemini but the subprocess failed before it could act.

**Pipeline result: FAILED after 3 iterations.**

---

## Human Assist Required

**What broke:** Test assertion `"SHOULD_NOT_APPEAR" not in out` was incorrect
given that dry_run output legitimately includes the command text.

**Fix:** Changed the test to use an unambiguous side-effect check:

```python
_sentinel = "/tmp/nazir_dryrun_sentinel"
out = safe_run_command(f"touch {_sentinel}", dry_run=True)
assert "DRY_RUN" in out
assert not os.path.exists(_sentinel)  # file not created → command did not execute
```

This is immune to the "does the command text appear in the description" ambiguity.

**Time to fix:** ~2 minutes.

**Lesson:** When writing tests for TDD-in-a-pipeline, use side-effect checks
(file creation, state change) rather than output string membership when the
command text and execution output could overlap.

---

## Final Results

| Metric | Value |
|--------|-------|
| Pipeline outcome | FAILED (Gemini correct, test spec wrong) |
| Iterations | 3 (1 code+test, 2 coder errors) |
| New delegations | +9 (planner + 3 coder calls) |
| Additional $ saved | +$1.7291 |
| Total $ saved lifetime | $6.9330 |
| Planner output | Perfect 6-step JSON plan |
| Coder output | Correct implementation on first attempt |
| Human intervention | Fix test assertion (2 min) |
| Final test score | 7/7 mission + 156/156 full suite |

## Failure Log (Honest)

| What failed | Why | Severity |
|-------------|-----|----------|
| Pipeline exit | Test assertion ambiguous — Gemini's code was correct | Low |
| Iterations 2-3 | Gemini CLI rate limit / exit after long first call | Medium |
| Human assist needed | 1 test spec fix, ~2 min | Low |

## Verdict

Nazir can implement self-contained, well-specified features without intervention.
The architecture (plan → code → test → review → commit) works correctly.

The failure in this mission was in the test specification, not in any agent.
Gemini produced a correct implementation on the first try, from a correctly
structured plan from the Planner. The iteration limit is the weakest link —
if the test spec is wrong, the pipeline can't self-correct it.

**Implication for future missions:** Write acceptance tests with unambiguous
side-effect assertions before running the pipeline.

---

## Git History

Changes committed by Gemini (iteration 1):
- `mcp_server/tools/shell.py` — added `dry_run` parameter
- `mcp_server/server.py` — updated `run_command` MCP tool

Human fix:
- `tests/mission_01_test.py` — corrected test assertion

---

*Nazir Phase 9 — First Real Mission*
*Pop!_OS 22.04 · Gemini CLI 0.41.2 · Claude Code 2.1.157*
