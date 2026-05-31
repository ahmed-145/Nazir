"""
Nazir subagent orchestration layer — Phase 8.

Four specialized roles:
  planner  — Claude -p: breaks task into steps + acceptance criteria
  coder    — Gemini CLI: writes the code (1M context, @dir/ ingestion)
  tester   — runs test suite, feeds stderr back to coder on failure
  reviewer — Claude -p: reviews diff, returns APPROVED or REVISION_NEEDED

Pipeline:
  plan → [code → test]* → review → commit
              ↑____________|
           (on failure, up to max_iterations)

Dependency injection: pass custom agent classes to SubagentOrchestrator
for testing without external calls (no mocks library needed).
"""
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Type

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_TEST_COMMAND = f"python3 {PROJECT_ROOT}/test_all_phases.py"
DEFAULT_MAX_ITERATIONS = 3


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    role: str
    success: bool
    output: str
    data: dict = field(default_factory=dict)
    tokens_used: int = 0
    error: str = ""
    duration_s: float = 0.0


@dataclass
class PipelineResult:
    success: bool
    task: str
    plan: AgentResult = None
    iterations: list = field(default_factory=list)   # list of (code, test) pairs
    review: AgentResult = None
    committed: bool = False
    commit_hash: str = ""
    failure_reason: str = ""
    total_duration_s: float = 0.0
    dollars_saved: float = 0.0


class AgentError(Exception):
    """Raised when an agent call fails unrecoverably."""


# ── Shared utilities ──────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Extract a JSON object from text that may be wrapped in markdown fences.
    Returns {} if no valid JSON found.
    """
    # Try ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try bare outermost JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _run_claude(prompt: str, timeout: int = 120) -> str:
    """
    Call claude -p headlessly. Returns stdout text.
    Raises AgentError on non-zero exit with no output.
    """
    result = subprocess.run(
        ["claude", "--dangerously-skip-permissions", "-p", prompt],
        capture_output=True, text=True, timeout=timeout,
        cwd=str(PROJECT_ROOT), stdin=subprocess.DEVNULL,
    )
    out = result.stdout.strip()
    if result.returncode != 0 and not out:
        raise AgentError(
            f"claude -p exited {result.returncode}: {result.stderr[:300]}"
        )
    return out


def _git_diff_staged() -> str:
    """Return the current staged diff (empty string if nothing staged)."""
    r = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    return r.stdout


def _git_diff_head() -> str:
    """Return diff of working tree against HEAD."""
    r = subprocess.run(
        ["git", "diff", "HEAD"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    return r.stdout


def _record_delegation(task_name: str, output: str) -> float:
    """
    Estimate and record a Gemini delegation in the metrics DB.
    Returns dollars_saved.
    """
    try:
        from orchestrator.metrics import record
        # Estimate tokens from output length (rough: 4 chars ≈ 1 token)
        est_tokens = max(len(output) // 4, 10)
        fake_stats = {
            "models": {
                "gemini-2.0-flash": {
                    "api": {"totalLatencyMs": 0},
                    "tokens": {
                        "input": est_tokens,
                        "candidates": est_tokens // 4,
                        "cached": 0,
                        "total": est_tokens + est_tokens // 4,
                    },
                }
            }
        }
        return record(stats=fake_stats, task_name=task_name, prompt=task_name[:120])
    except Exception:
        return 0.0


# ── Agent roles ───────────────────────────────────────────────────────────────

class PlannerAgent:
    """
    Claude-driven planner. Breaks a task into ordered steps with
    acceptance criteria and a list of files likely to be modified.
    """

    SYSTEM = (
        "You are the Nazir planner agent. Your job is to break a software task "
        "into clear, ordered implementation steps with acceptance criteria. "
        "Always respond with ONLY a JSON object — no prose, no markdown fences.\n\n"
        "Schema:\n"
        '{"steps": ["step 1", ...], '
        '"acceptance_criteria": ["criterion 1", ...], '
        '"files_to_modify": ["relative/path", ...], '
        '"estimated_complexity": "low|medium|high"}'
    )

    def run(self, task: str, context: dict = None) -> AgentResult:
        t0 = time.time()
        prompt = f"{self.SYSTEM}\n\nTask: {task}"
        try:
            raw = _run_claude(prompt, timeout=90)
        except AgentError as e:
            return AgentResult("planner", False, "", {}, 0, str(e),
                               time.time() - t0)

        data = _extract_json(raw)
        success = bool(data.get("steps"))
        if not success:
            # Tolerate: wrap raw text as a single step
            data = {
                "steps": [raw[:500]] if raw else ["(planner returned no steps)"],
                "acceptance_criteria": [],
                "files_to_modify": [],
                "estimated_complexity": "unknown",
            }
        return AgentResult(
            "planner", True, raw, data,
            len(raw) // 4, "", time.time() - t0
        )


class CoderAgent:
    """
    Gemini CLI-driven coder. Uses run_gemini() with session tracking
    so follow-up iterations (on test failure) resume in the same session.
    """

    def run(self, task: str, context: dict = None) -> AgentResult:
        from orchestrator.gemini_runner import run_gemini, ACTIVE_SESSIONS
        context = context or {}
        t0 = time.time()

        plan   = context.get("plan", {})
        feedback = context.get("test_feedback", "")
        iteration = context.get("iteration", 0)

        steps_text = "\n".join(
            f"  {i+1}. {s}" for i, s in enumerate(plan.get("steps", []))
        )
        files_text = ", ".join(plan.get("files_to_modify", [])) or "(determine from context)"

        prompt_parts = [
            f"Task: {task}",
            "",
            "Implementation plan:",
            steps_text or "  (no plan provided — use your best judgment)",
            "",
            f"Files likely to need changes: {files_text}",
            "",
            "Implement the required changes. Write complete, working code.",
            "Use @" + str(PROJECT_ROOT) + "/ to read files as needed.",
            "Make only the changes required by the task. Do not refactor unrelated code.",
        ]
        if feedback:
            prompt_parts += [
                "",
                f"IMPORTANT — previous test run failed (iteration {iteration}).",
                "Fix these failures:",
                feedback[:2000],
            ]

        prompt = "\n".join(prompt_parts)
        task_key = f"coder-{task[:40].replace(' ', '-')}"

        try:
            response = run_gemini(prompt, task_name=task_key)
            dollars = _record_delegation(task_key, response)
            return AgentResult(
                "coder", True, response, {"dollars_saved": dollars},
                len(response) // 4, "", time.time() - t0
            )
        except Exception as e:
            return AgentResult("coder", False, "", {}, 0, str(e), time.time() - t0)


class TesterAgent:
    """
    Runs the project test suite and reports pass/fail + stderr for feedback.
    """

    def __init__(self, test_command: str = None):
        self.test_command = test_command or DEFAULT_TEST_COMMAND

    def run(self, task: str, context: dict = None) -> AgentResult:
        t0 = time.time()
        try:
            result = subprocess.run(
                self.test_command,
                shell=True, capture_output=True, text=True,
                timeout=300, cwd=str(PROJECT_ROOT),
            )
            passed = result.returncode == 0
            output = result.stdout + result.stderr

            # Extract failure summary (lines with FAIL keyword)
            fail_lines = [
                line for line in output.splitlines()
                if re.search(r"\bFAIL\b", line, re.IGNORECASE)
            ]
            feedback = "\n".join(fail_lines[:20]) if fail_lines else output[-1000:]

            return AgentResult(
                "tester", passed, output,
                {"passed": passed, "feedback": feedback,
                 "returncode": result.returncode},
                0, "" if passed else feedback, time.time() - t0
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                "tester", False, "", {}, 0, "test suite timed out (300s)",
                time.time() - t0
            )
        except Exception as e:
            return AgentResult("tester", False, "", {}, 0, str(e), time.time() - t0)


class ReviewerAgent:
    """
    Claude-driven reviewer. Receives the task description + git diff,
    returns APPROVED or REVISION_NEEDED with feedback.
    """

    SYSTEM = (
        "You are the Nazir reviewer agent. Review a git diff for correctness. "
        "Check: does it implement the task? any obvious bugs? any unintended changes?\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"decision": "APPROVED" | "REVISION_NEEDED", '
        '"feedback": "one paragraph", '
        '"issues": ["issue 1", ...]}'
    )

    def run(self, task: str, context: dict = None) -> AgentResult:
        context = context or {}
        t0 = time.time()

        diff = context.get("diff") or _git_diff_head()
        if not diff.strip():
            # Nothing changed — auto-approve (coder may have been a no-op)
            data = {"decision": "APPROVED", "feedback": "No diff — nothing to review.", "issues": []}
            return AgentResult("reviewer", True, "APPROVED (no diff)", data, 0, "", time.time() - t0)

        prompt = (
            f"{self.SYSTEM}\n\n"
            f"Task implemented: {task}\n\n"
            f"Git diff (truncated to 4000 chars):\n"
            f"{diff[:4000]}"
        )

        try:
            raw = _run_claude(prompt, timeout=90)
        except AgentError as e:
            return AgentResult("reviewer", False, "", {}, 0, str(e), time.time() - t0)

        data = _extract_json(raw)
        if not data.get("decision"):
            # Fallback: if "APPROVED" appears in raw text, accept it
            if "APPROVED" in raw.upper():
                data = {"decision": "APPROVED", "feedback": raw[:500], "issues": []}
            else:
                data = {"decision": "REVISION_NEEDED", "feedback": raw[:500], "issues": []}

        approved = data["decision"] == "APPROVED"
        return AgentResult(
            "reviewer", approved, raw, data,
            len(raw) // 4, "" if approved else data.get("feedback", ""),
            time.time() - t0
        )


# ── Orchestrator ──────────────────────────────────────────────────────────────

class SubagentOrchestrator:
    """
    Runs the full plan → [code → test]* → review → commit pipeline.

    Dependency injection: pass custom agent classes for testing.
    """

    def __init__(
        self,
        planner_cls:  Type = None,
        coder_cls:    Type = None,
        tester_cls:   Type = None,
        reviewer_cls: Type = None,
        test_command: str  = None,
    ):
        self.planner_cls  = planner_cls  or PlannerAgent
        self.coder_cls    = coder_cls    or CoderAgent
        self.tester_cls   = tester_cls   or TesterAgent
        self.reviewer_cls = reviewer_cls or ReviewerAgent
        self.test_command = test_command

    def _make_tester(self) -> TesterAgent:
        # Always pass test_command via constructor so subclasses can record it
        return self.tester_cls(test_command=self.test_command)

    def run_pipeline(
        self,
        task: str,
        dry_run: bool = False,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> PipelineResult:
        """
        Execute the full subagent pipeline.

        dry_run=True: runs plan/code/test/review but skips the git commit.
        Returns PipelineResult describing what happened at each stage.
        """
        t0 = time.time()
        result = PipelineResult(success=False, task=task)

        # ── 1. Plan ──────────────────────────────────────────────────────────
        planner = self.planner_cls()
        result.plan = planner.run(task)
        if not result.plan.success:
            result.failure_reason = f"planner failed: {result.plan.error}"
            result.total_duration_s = time.time() - t0
            return result

        # ── 2. Code → Test loop ───────────────────────────────────────────────
        coder   = self.coder_cls()
        tester  = self._make_tester()
        test_feedback = ""
        last_test: Optional[AgentResult] = None

        for i in range(max_iterations):
            code_result = coder.run(task, context={
                "plan":          result.plan.data,
                "test_feedback": test_feedback,
                "iteration":     i,
            })
            test_result = tester.run(task, context={"iteration": i})
            result.iterations.append((code_result, test_result))

            if test_result.success:
                last_test = test_result
                break

            test_feedback = test_result.data.get("feedback", test_result.error)
            last_test = test_result

            if i == max_iterations - 1:
                result.failure_reason = (
                    f"tests still failing after {max_iterations} iterations: "
                    f"{test_feedback[:200]}"
                )
                result.total_duration_s = time.time() - t0
                return result

        # ── 3. Review ─────────────────────────────────────────────────────────
        reviewer = self.reviewer_cls()
        result.review = reviewer.run(task, context={"diff": _git_diff_head()})

        if not result.review.success:
            result.failure_reason = (
                f"review rejected: {result.review.data.get('feedback', result.review.error)[:300]}"
            )
            result.total_duration_s = time.time() - t0
            return result

        # ── 4. Commit ─────────────────────────────────────────────────────────
        if not dry_run:
            try:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(PROJECT_ROOT), check=True, capture_output=True
                )
                commit_msg = f"agent: {task[:72]}"
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    cwd=str(PROJECT_ROOT), check=True, capture_output=True
                )
                r = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(PROJECT_ROOT), capture_output=True, text=True
                )
                result.commit_hash = r.stdout.strip()
                result.committed = True
            except subprocess.CalledProcessError as e:
                result.failure_reason = f"git commit failed: {e.stderr.decode()[:200]}"
                result.total_duration_s = time.time() - t0
                return result
        else:
            result.committed = False  # dry run: review passed, commit skipped

        # Sum dollars saved from coder delegations
        result.dollars_saved = sum(
            cr.data.get("dollars_saved", 0.0)
            for cr, _ in result.iterations
        )

        result.success = True
        result.total_duration_s = time.time() - t0
        return result


# ── Convenience helpers (for MCP tools + CLI) ─────────────────────────────────

def run_agent(role: str, task: str, context: dict = None) -> AgentResult:
    """
    Run a single named agent role.
    role: "planner" | "coder" | "tester" | "reviewer"
    """
    agents = {
        "planner":  PlannerAgent,
        "coder":    CoderAgent,
        "tester":   TesterAgent,
        "reviewer": ReviewerAgent,
    }
    if role not in agents:
        raise AgentError(f"Unknown role '{role}'. Valid: {list(agents)}")
    return agents[role]().run(task, context or {})


def pipeline_summary(result: PipelineResult) -> str:
    """Human-readable summary of a PipelineResult."""
    status = "✓ SUCCESS" if result.success else "✗ FAILED"
    lines = [
        f"Pipeline {status}: {result.task[:60]}",
        f"  Duration: {result.total_duration_s:.1f}s",
        f"  Iterations: {len(result.iterations)}",
    ]
    if result.plan:
        steps = result.plan.data.get("steps", [])
        lines.append(f"  Plan: {len(steps)} steps")
    for i, (cr, tr) in enumerate(result.iterations):
        t = "✓" if tr.success else "✗"
        lines.append(f"  Iteration {i+1}: coder={cr.success} tester={t}")
    if result.review:
        decision = result.review.data.get("decision", "?")
        lines.append(f"  Review: {decision}")
    if result.committed:
        lines.append(f"  Committed: {result.commit_hash}")
    if not result.success:
        lines.append(f"  Reason: {result.failure_reason}")
    if result.dollars_saved:
        lines.append(f"  $ saved: ${result.dollars_saved:.4f}")
    return "\n".join(lines)
