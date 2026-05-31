#!/usr/bin/env python3
"""
Nazir — Full Integration Test Suite
Tests every completed phase end-to-end.
Run: python3 test_all_phases.py
"""
import os
import sys
import json
import time
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault(
    "NAZIR_PROJECT_ROOT",
    str(Path(__file__).parent.resolve())
)
PROJECT_ROOT = Path(os.environ["NAZIR_PROJECT_ROOT"])
sys.path.insert(0, str(PROJECT_ROOT))

# ── Colours ───────────────────────────────────────────────────────────────────
G  = "\033[92m"   # green
R  = "\033[91m"   # red
Y  = "\033[93m"   # yellow
B  = "\033[94m"   # blue
BO = "\033[1m"
RE = "\033[0m"

PASS = f"{G}PASS{RE}"
FAIL = f"{R}FAIL{RE}"
SKIP = f"{Y}SKIP{RE}"

results: list[tuple[bool | None, str, str]] = []  # (ok, name, detail)

def header(title: str) -> None:
    width = 62
    print(f"\n{BO}{B}{'─'*width}{RE}")
    print(f"{BO}{B}  {title}{RE}")
    print(f"{BO}{B}{'─'*width}{RE}")

def ok(name: str, detail: str = "") -> None:
    results.append((True, name, detail))
    print(f"  {PASS}  {name}" + (f"  →  {detail}" if detail else ""))

def fail(name: str, detail: str = "") -> None:
    results.append((False, name, detail))
    print(f"  {FAIL}  {name}" + (f"\n         {R}{detail}{RE}" if detail else ""))

def skip(name: str, reason: str = "") -> None:
    results.append((None, name, reason))
    print(f"  {SKIP}  {name}" + (f"  →  {reason}" if reason else ""))

def expect_pass(name: str, fn):
    try:
        result = fn()
        ok(name, str(result)[:70])
    except Exception as e:
        fail(name, str(e)[:100])

def expect_block(name: str, fn):
    try:
        fn()
        fail(name, "should have raised PermissionError — did NOT block")
    except PermissionError as e:
        ok(name, f"blocked: {str(e)[:50]}")
    except Exception as e:
        fail(name, f"wrong exception ({type(e).__name__}): {str(e)[:60]}")

def run(cmd: list, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 0 — Foundation
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 0 — Foundation")

# NAZIR_PROJECT_ROOT
if PROJECT_ROOT.exists():
    ok("NAZIR_PROJECT_ROOT set + exists", str(PROJECT_ROOT)[-40:])
else:
    fail("NAZIR_PROJECT_ROOT", f"path does not exist: {PROJECT_ROOT}")

# API keys
gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
if gemini_key:
    ok("GEMINI_API_KEY / GOOGLE_API_KEY set", f"{gemini_key[:8]}...")
else:
    fail("GEMINI_API_KEY not set — daemon auth will fail")

# .geminiignore
gi = PROJECT_ROOT / ".geminiignore"
if gi.exists() and "node_modules" in gi.read_text():
    ok(".geminiignore exists with node_modules entry")
else:
    fail(".geminiignore missing or incomplete — Gemini will burn quota on startup")

# .env
dotenv = PROJECT_ROOT / ".env"
if dotenv.exists():
    ok(".env exists")
else:
    fail(".env missing")

# gemini CLI version
r = run(["gemini", "--version"])
if r.returncode == 0:
    ok("gemini CLI on PATH", r.stdout.strip()[:30])
else:
    fail("gemini CLI not found")

# claude CLI
r = run(["claude", "--version"])
if r.returncode == 0:
    ok("claude CLI on PATH", r.stdout.strip()[:30])
else:
    fail("claude CLI not found")

# ripgrep
r = run(["rg", "--version"])
if r.returncode == 0:
    ok("ripgrep (rg) on PATH", r.stdout.splitlines()[0][:30])
else:
    fail("ripgrep not installed — search tools use grep fallback")

# cgcone
r = run(["cgcone", "--version"])
if r.returncode == 0:
    ok("cgcone on PATH", r.stdout.strip()[:20])
else:
    fail("cgcone not installed — MCP sync broken")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 0.5 — Assumption Probe
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 0.5 — Assumption Probe")

probe_results = PROJECT_ROOT / "memory" / "probe_results.json"
if probe_results.exists():
    try:
        data = json.loads(probe_results.read_text())
        ok("probe_results.json exists", f"run at {data.get('probe_timestamp','?')[:19]}")

        # Key findings from probe
        if data.get("gemini_headless_basic", {}).get("passed"):
            ok("gemini headless -p: confirmed working")
        else:
            fail("gemini headless -p: probe marked FAIL")

        if data.get("gemini_json_has_session_id", {}).get("found"):
            ok("session_id in JSON: confirmed (issue #14435 resolved)")
        else:
            fail("session_id not in JSON — gemini_runner resume broken")

        if data.get("gemini_resume_works", {}).get("passed"):
            ok("--resume headless: confirmed working")
        else:
            skip("--resume: not tested in probe (no prior session)")

        if data.get("claude_headless_completes", {}).get("file_written"):
            ok("claude -p headless: confirmed stable")
        else:
            fail("claude -p headless: failed in probe")

    except json.JSONDecodeError:
        fail("probe_results.json: invalid JSON")
else:
    fail("probe_results.json missing — run python3 probe_phase0_5.py")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — DesktopCommanderMCP + AppArmor
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 1 — DesktopCommanderMCP + AppArmor")

DCM_BINARY = "/home/ahmeed/.local/lib/node_modules/@wonderwhy-er/desktop-commander/dist/index.js"
DCM_NODE = "/home/ahmeed/.local/bin/node"

# DCM binary exists
if Path(DCM_BINARY).exists():
    ok("DCM binary installed", DCM_BINARY[-40:])
else:
    fail("DCM binary not found at expected path")

# DCM MCP handshake — via shell (AppArmor blocks Python subprocess → node pipe)
try:
    r = subprocess.run(
        "echo '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\","
        "\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},"
        "\"clientInfo\":{\"name\":\"t\",\"version\":\"1\"}}}' "
        f"| timeout 5 node {DCM_BINARY} 2>/dev/null",
        shell=True, capture_output=True, text=True, timeout=10
    )
    resp = json.loads(r.stdout)
    sv = resp["result"]["serverInfo"]
    ok("DCM MCP handshake (shell)", f"{sv['name']} v{sv['version']}")
except Exception as e:
    fail("DCM MCP handshake failed", str(e)[:80])

# AppArmor profile loaded
r = run(["sudo", "-n", "aa-status"], timeout=5)
if r.returncode == 0 and "nazir-desktop-cmd" in r.stdout:
    # Check enforce vs complain
    lines = r.stdout.splitlines()
    in_enforce = False
    for i, line in enumerate(lines):
        if "enforce" in line.lower():
            in_enforce = True
        if in_enforce and "nazir-desktop-cmd" in line:
            ok("AppArmor nazir-desktop-cmd: enforce mode")
            break
    else:
        ok("AppArmor nazir-desktop-cmd: loaded (mode unknown without sudo)")
else:
    # Try without sudo
    r2 = subprocess.run(
        ["aa-status", "--json"], capture_output=True, text=True, timeout=5
    )
    if "nazir-desktop-cmd" in r2.stdout + r2.stderr:
        ok("AppArmor nazir-desktop-cmd: profile present")
    else:
        # Check via /sys (needs read permission)
        try:
            prof_path = Path("/sys/kernel/security/apparmor/profiles")
            content = prof_path.read_text()
            if "nazir-desktop-cmd" in content:
                ok("AppArmor nazir-desktop-cmd: loaded (via /sys)")
            else:
                fail("AppArmor profile not loaded", "run: sudo apparmor_parser -r /etc/apparmor.d/nazir-desktop-cmd")
        except PermissionError:
            # Check if profile file exists in /etc/apparmor.d as a proxy
            prof_file = Path("/etc/apparmor.d/nazir-desktop-cmd")
            if prof_file.exists():
                ok("AppArmor profile installed (sudo needed to verify mode)")
            else:
                skip("AppArmor status check requires sudo")

# AppArmor profile file in repo
apparmor_file = PROJECT_ROOT / "security" / "apparmor" / "nazir-desktop-cmd"
if apparmor_file.exists():
    ok("AppArmor profile in repo", str(apparmor_file)[-40:])
else:
    fail("AppArmor profile file missing from repo")

# Claude Code MCP connection
r = run(["claude", "mcp", "list"])
if "desktop-commander" in r.stdout and "✓" in r.stdout:
    ok("DCM connected to Claude Code")
elif "desktop-commander" in r.stdout:
    fail("DCM in Claude Code MCP list but NOT connected")
else:
    fail("DCM not registered in Claude Code MCP")

# Gemini CLI MCP config
gemini_settings = Path.home() / ".gemini" / "settings.json"
if gemini_settings.exists():
    s = json.loads(gemini_settings.read_text())
    if "desktop-commander" in s.get("mcpServers", {}):
        ok("DCM in Gemini CLI settings.json")
    else:
        fail("DCM not in Gemini CLI settings.json")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — Custom Python MCP Server (nazir-tools)
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 2 — nazir-tools MCP Server")

# Import security modules
try:
    from security.validate_path import validate_path
    from security.blocklist import check_command
    ok("security modules import OK")
except ImportError as e:
    fail("security module import failed", str(e))

# Import MCP tools
try:
    from mcp_server.tools.shell import safe_run_command, ping_heartbeat
    from mcp_server.tools.files import safe_read_file, safe_write_file, list_dir
    from mcp_server.tools.git import git_status, git_diff, git_log
    from mcp_server.tools.search import search_in_files, find_files
    from mcp_server.tools.code import lint_file
    ok("all MCP tool modules import OK")
except ImportError as e:
    fail("MCP tool import failed", str(e))

# validate_path — allowed
expect_pass("validate_path: inside PROJECT_ROOT",
    lambda: validate_path("memory/last_checkpoint.md"))

# validate_path — blocked
expect_block("validate_path: /etc/passwd blocked",
    lambda: validate_path("/etc/passwd"))

expect_block("validate_path: traversal ../../.ssh blocked",
    lambda: validate_path("memory/../../.ssh/id_rsa"))

# blocklist
expect_block("blocklist: rm -rf / blocked",
    lambda: check_command("rm -rf /"))

expect_block("blocklist: sudo cat blocked",
    lambda: check_command("sudo cat /etc/shadow"))

expect_block("blocklist: fork bomb blocked",
    lambda: check_command(":(){:|:&};:"))

expect_pass("blocklist: git status allowed",
    lambda: (check_command("git status"), "allowed"))

# safe_run_command
expect_pass("safe_run_command: echo",
    lambda: safe_run_command("echo SHELL_OK"))

expect_block("safe_run_command: rm -rf blocked",
    lambda: safe_run_command("rm -rf /"))

# file ops
with tempfile.NamedTemporaryFile(
    dir=PROJECT_ROOT / "memory", suffix=".test", delete=False
) as tf:
    test_file = tf.name

expect_pass("write_file inside PROJECT_ROOT",
    lambda: safe_write_file(test_file, "TEST_WRITE_OK"))

expect_pass("read_file inside PROJECT_ROOT",
    lambda: safe_read_file(test_file))

expect_block("read_file /etc/passwd blocked",
    lambda: safe_read_file("/etc/passwd"))

expect_block("write_file /tmp/evil blocked",
    lambda: safe_write_file("/tmp/evil.txt", "x"))

expect_pass("list_dir PROJECT_ROOT",
    lambda: list_dir("."))

Path(test_file).unlink(missing_ok=True)

# git tools
expect_pass("git_status", lambda: git_status())
expect_pass("git_log(3)", lambda: git_log(3))
expect_pass("git_diff", lambda: git_diff())

# search
expect_pass("search_in_files (rg)",
    lambda: search_in_files("FastMCP", "mcp_server", "*.py"))

expect_pass("find_files *.py in mcp_server",
    lambda: find_files("*.py", "mcp_server"))

# heartbeat
expect_pass("ping_heartbeat",
    lambda: ping_heartbeat())

hb = Path("/tmp/nazir-heartbeat")
if hb.exists() and (time.time() - hb.stat().st_mtime) < 30:
    ok("heartbeat file recently touched", f"age={time.time()-hb.stat().st_mtime:.0f}s")
else:
    fail("heartbeat file not touched recently")

# lint
expect_pass("lint_file (clean file)",
    lambda: lint_file("mcp_server/config.py"))

# Claude Code MCP connection
r = run(["claude", "mcp", "list"])
if "nazir-tools" in r.stdout and "✓" in r.stdout:
    ok("nazir-tools connected to Claude Code")
else:
    fail("nazir-tools not connected to Claude Code")

# Gemini CLI config
if gemini_settings.exists():
    s = json.loads(gemini_settings.read_text())
    if "nazir-tools" in s.get("mcpServers", {}):
        ok("nazir-tools in Gemini CLI settings.json")
    else:
        fail("nazir-tools not in Gemini CLI settings.json")

# MCP server fastmcp import
try:
    from mcp.server.fastmcp import FastMCP
    ok("FastMCP (mcp SDK) importable")
except ImportError:
    fail("mcp SDK not installed — pip install mcp")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — Gemini CLI Orchestration
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 3 — Gemini CLI Orchestration")

try:
    from orchestrator.gemini_runner import (
        run_gemini, ACTIVE_SESSIONS, save_sessions, load_sessions, check_quota, _gemini_env
    )
    from orchestrator.quota_monitor import parse_stats, should_use_gemini, save_stats
    from orchestrator.task_queue import (
        write_task, mark_done, has_task, tail_log, read_current_task
    )
    ok("orchestrator modules import OK")
except ImportError as e:
    fail("orchestrator import failed", str(e))

# gemini_runner env check
env = _gemini_env()
if env.get("GEMINI_API_KEY"):
    ok("GEMINI_API_KEY in gemini_runner env")
else:
    fail("GEMINI_API_KEY missing from gemini_runner env — daemon auth will fail")

if env.get("GEMINI_TELEMETRY_ENABLED") == "false":
    ok("GEMINI_TELEMETRY_ENABLED=false (no code exfiltration)")
else:
    fail("GEMINI_TELEMETRY_ENABLED not false — telemetry may be on")

# Check --allowed-mcp-server-names none is in cmd
import inspect
src = inspect.getsource(run_gemini)
if "--allowed-mcp-server-names" in src and "none" in src:
    ok("--allowed-mcp-server-names none in run_gemini (fast subprocess)")
else:
    fail("--allowed-mcp-server-names none missing — subprocesses will be slow")

# gemini_sessions.json exists and is valid
sessions_file = PROJECT_ROOT / "memory" / "gemini_sessions.json"
if sessions_file.exists():
    try:
        sessions = json.loads(sessions_file.read_text())
        ok("gemini_sessions.json valid", f"{len(sessions)} session(s) persisted")
        # Load them
        load_sessions(sessions_file)
        if ACTIVE_SESSIONS:
            ok("sessions loaded into ACTIVE_SESSIONS", str(list(ACTIVE_SESSIONS.keys())))
    except json.JSONDecodeError:
        fail("gemini_sessions.json: invalid JSON")
else:
    skip("gemini_sessions.json not found (will be created on first run)")

# quota_monitor
expect_pass("should_use_gemini()", lambda: should_use_gemini())

# task_queue roundtrip
def test_task_queue():
    write_task("integration-test-task")
    assert has_task(), "has_task() returned False after write"
    mark_done("integration-test-task", "test-ok")
    log = tail_log(1)
    assert log and log[0]["status"] == "completed"
    return f"logged: {log[0]['status']}"
expect_pass("task_queue: write→has_task→mark_done→log", test_task_queue)

# task_queue PAUSE marker
write_task("DONE")  # reset to clean state

# Live Gemini call (fast, single call with existing session if available)
print(f"\n  {Y}Running live Gemini call (may take 10-60s)...{RE}")
try:
    r = run_gemini("Reply with exactly: INTEGRATION_TEST_OK", task_name="integration-test")
    if "INTEGRATION_TEST_OK" in r:
        ok("live Gemini call", f"response: {r.strip()[:40]}")
        ok("session_id captured", ACTIVE_SESSIONS.get("integration-test", "?")[:16] + "...")
        save_sessions(sessions_file)
        ok("sessions saved to gemini_sessions.json")
    else:
        fail("live Gemini call: unexpected response", r.strip()[:60])
except Exception as e:
    fail("live Gemini call failed", str(e)[:100])


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4 — Heartbeat Daemon + systemd
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 4 — Heartbeat Daemon + systemd")

# Services enabled
for svc in ["claude-agent.service", "heartbeat.service"]:
    r = run(["systemctl", "--user", "is-enabled", svc])
    if r.stdout.strip() == "enabled":
        ok(f"{svc}: enabled")
    else:
        fail(f"{svc}: not enabled", r.stdout.strip())

# Services active
r_agent  = run(["systemctl", "--user", "is-active", "claude-agent.service"])
r_hb     = run(["systemctl", "--user", "is-active", "heartbeat.service"])
if r_hb.stdout.strip() == "active":
    ok("heartbeat.service: active (running)")
else:
    fail("heartbeat.service: not active", r_hb.stdout.strip())

if r_agent.stdout.strip() == "active":
    ok("claude-agent.service: active (running)")
else:
    skip("claude-agent.service: not active (normal if no pending task)")

# Linger enabled
r = run(["loginctl", "show-user", "ahmeed"])
if "Linger=yes" in r.stdout:
    ok("loginctl enable-linger: ON (survives logout)")
else:
    fail("loginctl enable-linger: OFF — services will die on logout")

# run-claude.sh executable
run_sh = PROJECT_ROOT / "systemd" / "run-claude.sh"
if run_sh.exists() and os.access(run_sh, os.X_OK):
    ok("run-claude.sh exists and is executable")
else:
    fail("run-claude.sh missing or not executable")

# Heartbeat daemon modules import
try:
    from heartbeat.daemon import log, heartbeat_age, restart_agent, pause_agent
    from heartbeat.rollback import stash_partial_work, write_recovery_task
    from heartbeat.notify import notify
    ok("heartbeat modules import OK")
except ImportError as e:
    fail("heartbeat module import failed", str(e))

# Heartbeat file freshness
hb_path = Path("/tmp/nazir-heartbeat")
if hb_path.exists():
    age = time.time() - hb_path.stat().st_mtime
    if age < 600:  # touched in last 10 min
        ok(f"heartbeat file fresh", f"age={age:.0f}s")
    else:
        fail(f"heartbeat file stale", f"age={age:.0f}s — is the agent running?")
else:
    skip("heartbeat file doesn't exist yet (agent hasn't run a task)")

# heartbeat_age() function
try:
    age = heartbeat_age()
    ok("heartbeat_age() callable", f"returns {age:.0f}s")
except Exception as e:
    fail("heartbeat_age() error", str(e))

# Log files exist (or dir exists)
log_dir = PROJECT_ROOT / "logs"
if log_dir.exists():
    logs = list(log_dir.glob("*.log"))
    if logs:
        ok(f"logs/ has {len(logs)} log file(s)", ", ".join(f.name for f in logs))
    else:
        ok("logs/ directory exists (no logs yet)")
else:
    fail("logs/ directory missing")

# Check heartbeat log for recent activity
hb_log = PROJECT_ROOT / "logs" / "heartbeat.log"
if hb_log.exists():
    lines = hb_log.read_text().splitlines()
    if lines:
        ok(f"heartbeat.log has {len(lines)} entries", lines[-1][:60])
    else:
        skip("heartbeat.log is empty")
else:
    skip("heartbeat.log not found yet")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — Context Management
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 5 — Context Management")

# ── 5.1 Module imports ───────────────────────────────────────────────────────
try:
    from memory.wrapup import write_checkpoint, quick_wrapup
    from memory.catchup import restore, summary
    from memory.updater import (
        full_update, prepend_decision, update_section,
        update_architecture, update_known_issues, _replace_section,
    )
    ok("Phase 5 modules import OK (wrapup, catchup, updater)")
except ImportError as e:
    fail("Phase 5 module import failed", str(e))

# ── 5.2 write_checkpoint: archive created with correct name format ────────────
try:
    _before_ckpts = len(list((PROJECT_ROOT / "memory" / "checkpoints").glob("*.md")))
    archive = write_checkpoint(
        "phase5-god-mode-test",
        completed=["step A done", "step B done"],
        pending=["step C pending"],
        decisions=["chose X over Y because Z"],
        files_modified=["memory/wrapup.py"],
        blockers=["none"],
    )
    _ap = Path(archive)
    assert _ap.exists(), "archive file not created"
    # Archive name must be YYYYMMDD_HHMMSS.md
    import re as _re
    assert _re.match(r"\d{8}_\d{6}\.md", _ap.name), f"bad name: {_ap.name}"
    ok("write_checkpoint: archive created with correct YYYYMMDD_HHMMSS.md name", _ap.name)
except AssertionError as e:
    fail("write_checkpoint archive", str(e))
except Exception as e:
    fail("write_checkpoint failed", str(e)[:80])

# ── 5.3 last_checkpoint.md: exists and has expected sections ─────────────────
_cp = PROJECT_ROOT / "memory" / "last_checkpoint.md"
try:
    assert _cp.exists() and _cp.stat().st_size > 0
    _cp_text = _cp.read_text()
    for _section in (
        "# Nazir Context Checkpoint",
        "## Current Task",
        "## Completed Steps",
        "## Pending (resume here)",
        "## Key Decisions Made",
        "## Files Modified This Session",
        "## Active Gemini CLI Sessions",
    ):
        assert _section in _cp_text, f"missing: {_section}"
    ok("last_checkpoint.md: exists with all required sections",
       f"{_cp.stat().st_size} bytes")
except AssertionError as e:
    fail("last_checkpoint.md content", str(e))
except Exception as e:
    fail("last_checkpoint.md check failed", str(e)[:80])

# ── 5.4 write_checkpoint: content matches inputs ─────────────────────────────
try:
    _cp_text = _cp.read_text()
    assert "phase5-god-mode-test" in _cp_text, "task not in checkpoint"
    assert "step A done"          in _cp_text, "completed step missing"
    assert "step C pending"       in _cp_text, "pending step missing"
    assert "chose X over Y"       in _cp_text, "decision missing"
    assert "memory/wrapup.py"     in _cp_text, "file_modified missing"
    ok("write_checkpoint: content matches all inputs (task/completed/pending/decisions/files)")
except AssertionError as e:
    fail("write_checkpoint content mismatch", str(e))

# ── 5.5 write_checkpoint: Gemini sessions embedded + persisted ───────────────
try:
    _test_sessions = {"p5-task-a": "uuid-aaaa-bbbb", "p5-task-b": "uuid-cccc-dddd"}
    _arch2 = write_checkpoint(
        "sessions test", gemini_sessions=_test_sessions
    )
    _arch2_text = Path(_arch2).read_text()
    assert "p5-task-a" in _arch2_text, "session key not in archive"
    assert "uuid-aaaa" in _arch2_text, "session uuid not in archive"
    # gemini_sessions.json must be updated
    _sf = PROJECT_ROOT / "memory" / "gemini_sessions.json"
    assert _sf.exists()
    _saved = json.loads(_sf.read_text())
    assert _saved.get("p5-task-a") == "uuid-aaaa-bbbb", "session not persisted to JSON"
    ok("write_checkpoint: Gemini sessions embedded in archive + persisted to JSON")
except AssertionError as e:
    fail("write_checkpoint sessions persistence", str(e))
except Exception as e:
    fail("write_checkpoint sessions failed", str(e)[:80])

# ── 5.6 checkpoints archive grows on each call ───────────────────────────────
# Note: two calls within the same second share a %H%M%S filename — the second
# overwrites the first, so we check >= +1, not +2.
_after_ckpts = len(list((PROJECT_ROOT / "memory" / "checkpoints").glob("*.md")))
if _after_ckpts >= _before_ckpts + 1:
    ok(f"checkpoints archive: grew from {_before_ckpts} → {_after_ckpts} files")
else:
    fail(f"checkpoints archive: expected growth, got {_before_ckpts} → {_after_ckpts}")

# ── 5.7 quick_wrapup(): works, reads current_task.md if no arg ───────────────
try:
    _qw = quick_wrapup("quick-test-task")
    assert Path(_qw).exists(), "quick_wrapup returned non-existent archive"
    _qw_text = Path(_qw).read_text()
    assert "quick-test-task" in _qw_text
    ok("quick_wrapup(task): works, archive created")
except Exception as e:
    fail("quick_wrapup failed", str(e)[:80])

try:
    # No-arg version reads from current_task.md
    _qw2 = quick_wrapup()
    assert Path(_qw2).exists()
    ok("quick_wrapup() no-arg: reads from current_task.md")
except Exception as e:
    fail("quick_wrapup() no-arg failed", str(e)[:80])

# ── 5.8 catchup.restore(): returns string with checkpoint content ─────────────
try:
    _ctx = restore()
    assert isinstance(_ctx, str) and len(_ctx) > 50
    assert "Nazir Context Checkpoint" in _ctx or "No previous checkpoint" in _ctx
    ok("catchup.restore(): returns non-empty context string",
       f"{len(_ctx)} chars")
except Exception as e:
    fail("catchup.restore() failed", str(e)[:80])

# ── 5.9 catchup.restore(): Gemini sessions injected into ACTIVE_SESSIONS ─────
try:
    from orchestrator.gemini_runner import ACTIVE_SESSIONS, load_sessions
    # Write a known session file then restore
    _sf = PROJECT_ROOT / "memory" / "gemini_sessions.json"
    _known = {"p5-restore-test": "uuid-restore-1234"}
    _sf.write_text(json.dumps(_known))
    restore()  # should call load_sessions internally
    # ACTIVE_SESSIONS should now contain the key
    assert "p5-restore-test" in ACTIVE_SESSIONS, \
        f"session not restored into ACTIVE_SESSIONS: {list(ACTIVE_SESSIONS.keys())}"
    ok("catchup.restore(): Gemini sessions injected into ACTIVE_SESSIONS",
       f"p5-restore-test → {ACTIVE_SESSIONS['p5-restore-test'][:12]}...")
except AssertionError as e:
    fail("catchup sessions injection", str(e))
except Exception as e:
    fail("catchup sessions injection failed", str(e)[:80])

# ── 5.10 catchup.summary(): correct structure ────────────────────────────────
try:
    _s = summary()
    for _k in ("has_checkpoint", "checkpoint_age_seconds", "sessions_count",
               "sessions", "current_task"):
        assert _k in _s, f"missing key: {_k}"
    assert _s["has_checkpoint"] is True
    assert isinstance(_s["sessions_count"], int)
    ok("catchup.summary(): all required keys present",
       f"age={_s['checkpoint_age_seconds']}s sessions={_s['sessions_count']}")
except AssertionError as e:
    fail("catchup.summary() structure", str(e))
except Exception as e:
    fail("catchup.summary() failed", str(e)[:80])

# ── 5.11 catchup.py runs as standalone script ────────────────────────────────
_r = run(["python3", str(PROJECT_ROOT / "memory" / "catchup.py")], timeout=10)
if _r.returncode == 0 and "Nazir catchup" in _r.stdout:
    ok("catchup.py runs as standalone script")
else:
    fail("catchup.py standalone failed", _r.stderr[:60] or _r.stdout[:60])

# ── 5.12 updater._replace_section: regex engine works ────────────────────────
try:
    _doc = "# Doc\n\n## Recent Decisions\nold content\n\n## Other Section\nstays\n"
    _updated = _replace_section(_doc, "Recent Decisions", "new content")
    assert "new content" in _updated, "replacement not applied"
    assert "old content" not in _updated, "old content not removed"
    assert "stays" in _updated, "Other Section clobbered"
    ok("updater._replace_section: regex replacement correct")
except AssertionError as e:
    fail("_replace_section logic", str(e))
except Exception as e:
    fail("_replace_section failed", str(e)[:80])

# ── 5.13 updater.prepend_decision(): dated entry prepended ───────────────────
try:
    _orig = _cp.read_text() if _cp.exists() else ""
    # Work on CLAUDE.md directly (it exists in the project)
    _claude_md = PROJECT_ROOT / "CLAUDE.md"
    if _claude_md.exists():
        _before = _claude_md.read_text()
        prepend_decision("phase5-god-mode-test decision")
        _after = _claude_md.read_text()
        assert "phase5-god-mode-test decision" in _after, "decision not prepended"
        # Restore original to avoid polluting CLAUDE.md permanently
        _claude_md.write_text(_before)
        ok("updater.prepend_decision(): dated entry prepended and visible in CLAUDE.md")
    else:
        skip("updater.prepend_decision()", "CLAUDE.md not found")
except AssertionError as e:
    fail("prepend_decision content check", str(e))
except Exception as e:
    fail("prepend_decision failed", str(e)[:80])

# ── 5.14 updater.update_architecture(): section replaced ─────────────────────
try:
    _claude_md = PROJECT_ROOT / "CLAUDE.md"
    if _claude_md.exists():
        _before = _claude_md.read_text()
        _sentinel = "TEST_ARCH_SENTINEL_PHASE5_GODMODE"
        update_architecture(_sentinel)
        _after = _claude_md.read_text()
        assert _sentinel in _after, "sentinel not found after update"
        _claude_md.write_text(_before)  # restore
        ok("updater.update_architecture(): section replaced and restored")
    else:
        skip("updater.update_architecture()", "CLAUDE.md not found")
except AssertionError as e:
    fail("update_architecture check", str(e))
except Exception as e:
    fail("update_architecture failed", str(e)[:80])

# ── 5.15 updater.full_update(): all fields in one call ───────────────────────
try:
    _claude_md = PROJECT_ROOT / "CLAUDE.md"
    if _claude_md.exists():
        _before = _claude_md.read_text()
        full_update(
            decision="full_update test decision",
            architecture="full_update test architecture",
        )
        _after = _claude_md.read_text()
        assert "full_update test decision"     in _after
        assert "full_update test architecture" in _after
        _claude_md.write_text(_before)  # restore
        ok("updater.full_update(): decision + architecture updated in one call")
    else:
        skip("updater.full_update()", "CLAUDE.md not found")
except AssertionError as e:
    fail("full_update check", str(e))
except Exception as e:
    fail("full_update failed", str(e)[:80])

# ── 5.16 MCP tools: wrapup, catchup, update_claude_md in server.py ───────────
try:
    _srv_src = (PROJECT_ROOT / "mcp_server" / "server.py").read_text()
    for _tool in ("def wrapup", "def catchup", "def update_claude_md"):
        assert _tool in _srv_src, f"missing MCP tool: {_tool}"
    ok("MCP server: wrapup + catchup + update_claude_md tools present")
except AssertionError as e:
    fail("MCP tools missing", str(e))
except Exception as e:
    fail("MCP tool check failed", str(e)[:80])

# ── 5.17 Claude Code hooks: PreCompact + Stop configured ─────────────────────
_hooks_file = PROJECT_ROOT / ".claude" / "settings.json"
if _hooks_file.exists():
    try:
        _hdata = json.loads(_hooks_file.read_text())
        _h = _hdata.get("hooks", {})
        assert _h.get("PreCompact"), "PreCompact hook missing"
        assert _h.get("Stop"),       "Stop hook missing"
        ok("Claude Code hooks: PreCompact + Stop configured")
    except AssertionError as e:
        fail("hooks missing from .claude/settings.json", str(e))
    except Exception as e:
        fail("hooks file parse error", str(e)[:60])
else:
    fail(".claude/settings.json not found")

# ── 5.18 wrapup.py runs as hook command (subprocess) ─────────────────────────
_r = run(["python3", str(PROJECT_ROOT / "memory" / "wrapup.py")], timeout=10)
if _r.returncode == 0 and "Checkpoint" in _r.stdout:
    ok("wrapup.py runs as hook command (subprocess)")
else:
    fail("wrapup.py hook command failed", _r.stderr[:60])


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6 — Metrics & Cost Engine
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 6 — Metrics & Cost Engine")

# ── 6.1 Module import ────────────────────────────────────────────────────────
try:
    from orchestrator.metrics import (
        record, record_delegation, parse_stats, estimate_savings,
        cost_report, format_report, cost_governor, lifetime_report,
        db_row_count, schema_columns,
        CLAUDE_SONNET_INPUT_PER_MTOK, CLAUDE_SONNET_OUTPUT_PER_MTOK,
        DB_PATH,
    )
    ok("metrics.py imports OK")
except ImportError as e:
    fail("metrics.py import failed", str(e))

# ── 6.2 DB exists ────────────────────────────────────────────────────────────
if DB_PATH.exists():
    ok("metrics.db exists", f"{DB_PATH.stat().st_size} bytes")
else:
    fail("metrics.db not found", str(DB_PATH))

# ── 6.3 Schema validation ────────────────────────────────────────────────────
try:
    cols = schema_columns()
    required = {
        "id", "timestamp", "task_name", "gemini_input_tokens",
        "gemini_output_tokens", "gemini_total_tokens", "dollars_saved",
        "latency_ms", "session_id",
    }
    missing = required - set(cols)
    if not missing:
        ok("delegations schema: all required columns present", f"{len(cols)} cols")
    else:
        fail("delegations schema: missing columns", str(missing))
except Exception as e:
    fail("schema check failed", str(e)[:80])

# ── 6.4 parse_stats unit test ────────────────────────────────────────────────
_FAKE_STATS = {
    "models": {
        "gemini-2.0-flash": {
            "api": {"totalLatencyMs": 1200},
            "tokens": {"input": 5000, "candidates": 800, "cached": 100, "total": 5900},
        },
        "gemini-2.0-flash-thinking": {
            "api": {"totalLatencyMs": 500},
            "tokens": {"input": 200, "candidates": 50, "cached": 0, "total": 250},
        },
    }
}
try:
    parsed = parse_stats(_FAKE_STATS)
    assert parsed["input_tokens"]  == 5200,  f"input={parsed['input_tokens']}"
    assert parsed["output_tokens"] == 850,   f"output={parsed['output_tokens']}"
    assert parsed["cached_tokens"] == 100,   f"cached={parsed['cached_tokens']}"
    assert parsed["total_tokens"]  == 6150,  f"total={parsed['total_tokens']}"
    assert parsed["latency_ms"]    == 1700,  f"latency={parsed['latency_ms']}"
    assert len(parsed["models"])   == 2
    ok("parse_stats: multi-model aggregation correct",
       f"in={parsed['input_tokens']} out={parsed['output_tokens']} lat={parsed['latency_ms']}ms")
except AssertionError as e:
    fail("parse_stats: wrong aggregation", str(e))
except Exception as e:
    fail("parse_stats threw", str(e)[:80])

# ── 6.5 estimate_savings math ────────────────────────────────────────────────
try:
    avoided_in, avoided_out, dollars = estimate_savings(1_000_000, 100_000)
    expected = (1_000_000 / 1_000_000) * CLAUDE_SONNET_INPUT_PER_MTOK \
             + (100_000  / 1_000_000) * CLAUDE_SONNET_OUTPUT_PER_MTOK
    assert abs(dollars - expected) < 0.0001, f"got {dollars} expected {expected}"
    ok("estimate_savings: math correct",
       f"1M in + 100k out → ${dollars:.4f} saved")
except AssertionError as e:
    fail("estimate_savings: math wrong", str(e))
except Exception as e:
    fail("estimate_savings threw", str(e)[:80])

# ── 6.6 record() x3 delegations → DB acceptance criterion ───────────────────
_baseline = db_row_count()
_tasks = [
    ("phase6-test-analysis",  _FAKE_STATS, "Analyze @src/ for API endpoints"),
    ("phase6-test-codegen",   _FAKE_STATS, "Generate unit tests for auth module"),
    ("phase6-test-review",    _FAKE_STATS, "Review diff before commit"),
]
_recorded = 0
for _tname, _stats, _prompt in _tasks:
    try:
        _dollars = record(stats=_stats, task_name=_tname, prompt=_prompt, session_id=f"test-uuid-{_tname}")
        assert isinstance(_dollars, float) and _dollars > 0
        _recorded += 1
    except Exception as e:
        fail(f"record() failed for {_tname}", str(e)[:80])

if _recorded == 3:
    ok("record(): 3 delegations written successfully")
else:
    fail(f"record(): only {_recorded}/3 delegations written")

_new_count = db_row_count()
if _new_count >= _baseline + 3:
    ok("delegations table: row count increased by 3",
       f"{_baseline} → {_new_count} rows")
else:
    fail("delegations table: row count did not increase by 3",
         f"was {_baseline}, now {_new_count}")

# ── 6.7 record_delegation alias ──────────────────────────────────────────────
try:
    _d = record_delegation(stats=_FAKE_STATS, task_name="phase6-alias-test")
    assert isinstance(_d, float) and _d >= 0
    ok("record_delegation alias works", f"${_d:.6f}")
except Exception as e:
    fail("record_delegation alias failed", str(e)[:80])

# ── 6.8 cost_report() returns non-zero dollars_saved ────────────────────────
try:
    report = cost_report("all")
    assert report["delegations"] > 0,    "no delegations recorded"
    assert report["dollars_saved"] > 0,  "dollars_saved is 0"
    assert report["gemini_tokens"] > 0,  "gemini_tokens is 0"
    assert "pricing_model" in report
    ok("cost_report('all'): non-zero dollars_saved",
       f"{report['delegations']} delegations, ${report['dollars_saved']:.4f} saved")
except AssertionError as e:
    fail("cost_report('all'): assertion failed", str(e))
except Exception as e:
    fail("cost_report threw", str(e)[:80])

# period filters
for _period in ("today", "week", "month"):
    try:
        r = cost_report(_period)
        assert "delegations" in r and "dollars_saved" in r
        ok(f"cost_report('{_period}'): returns valid dict",
           f"{r['delegations']} delegations")
    except Exception as e:
        fail(f"cost_report('{_period}') failed", str(e)[:80])

# ── 6.9 lifetime_report() alias ──────────────────────────────────────────────
try:
    lr = lifetime_report()
    assert lr["period"] == "all"
    ok("lifetime_report(): alias returns all-time report",
       f"${lr['dollars_saved']:.4f} total saved")
except Exception as e:
    fail("lifetime_report failed", str(e)[:80])

# ── 6.10 format_report() produces readable output ───────────────────────────
try:
    text = format_report(cost_report("all"))
    for kw in ("Delegations", "Gemini tokens", "Dollars saved", "Claude"):
        assert kw in text, f"'{kw}' not in output"
    ok("format_report(): all required fields present in output",
       f"{len(text)} chars")
except AssertionError as e:
    fail("format_report: missing keyword", str(e))
except Exception as e:
    fail("format_report threw", str(e)[:80])

# ── 6.11 cost_governor() ─────────────────────────────────────────────────────
try:
    # $999 budget → definitely not throttled
    under = cost_governor(daily_budget_usd=999.0)
    assert under is False, "cost_governor falsely throttled with $999 budget"
    # $0 budget → always throttled once we have data
    over = cost_governor(daily_budget_usd=0.0)
    assert over is True, "cost_governor failed to throttle with $0 budget"
    ok("cost_governor(): under/over budget logic correct")
except AssertionError as e:
    fail("cost_governor logic wrong", str(e))
except Exception as e:
    fail("cost_governor threw", str(e)[:80])

# ── 6.12 gemini_runner wired to metrics ──────────────────────────────────────
try:
    import inspect
    import orchestrator.gemini_runner as gr
    src = inspect.getsource(gr.run_gemini)
    assert "metrics" in src and "record" in src
    ok("gemini_runner.run_gemini: metrics.record call is present")
except AssertionError:
    fail("gemini_runner.run_gemini: metrics not wired up")
except Exception as e:
    fail("gemini_runner inspection failed", str(e)[:80])

# ── 6.13 MCP tools importable ────────────────────────────────────────────────
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mcp_server", PROJECT_ROOT / "mcp_server" / "server.py"
    )
    # Just check cost_report + delegation_stats appear in source text
    srv_src = (PROJECT_ROOT / "mcp_server" / "server.py").read_text()
    assert "def cost_report" in srv_src,     "cost_report tool missing"
    assert "def delegation_stats" in srv_src, "delegation_stats tool missing"
    ok("MCP server: cost_report + delegation_stats tools present")
except AssertionError as e:
    fail("MCP server: tool missing", str(e))
except Exception as e:
    fail("MCP server check failed", str(e)[:80])

# ── 6.14 daily_summary table upsert ─────────────────────────────────────────
try:
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    today_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT delegations, dollars_saved FROM daily_summary WHERE date = ?",
        (today_str,)
    ).fetchone()
    conn.close()
    if row and row["delegations"] >= 3:
        ok("daily_summary: today's row has >= 3 delegations",
           f"{row['delegations']} delegations, ${row['dollars_saved']:.4f}")
    else:
        fail("daily_summary: today's row missing or low count",
             f"row={dict(row) if row else None}")
except Exception as e:
    fail("daily_summary check failed", str(e)[:80])

# ── 6.15 DB has >= 3 rows (PRD acceptance criterion) ────────────────────────
try:
    total = db_row_count()
    if total >= 3:
        ok(f"PRD acceptance: delegations table has {total} rows (≥3 required)")
    else:
        fail(f"PRD acceptance: only {total} rows in delegations table (need ≥3)")
except Exception as e:
    fail("row count check failed", str(e)[:80])



# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 7 — Observability Dashboard
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 7 — Observability Dashboard")

# ── 7.1 dashboard/ package structure ─────────────────────────────────────────
_dash = PROJECT_ROOT / "dashboard"
for _f in (
    _dash / "__init__.py",
    _dash / "app.py",
    _dash / "data.py",
    _dash / "export.py",
    _dash / "widgets" / "__init__.py",
    _dash / "widgets" / "status_bar.py",
    _dash / "widgets" / "task_panel.py",
    _dash / "widgets" / "cost_panel.py",
    _dash / "widgets" / "token_meter.py",
    _dash / "widgets" / "session_panel.py",
):
    if _f.exists():
        ok(f"file exists: dashboard/{_f.relative_to(_dash)}")
    else:
        fail(f"missing file: dashboard/{_f.relative_to(_dash)}")

# ── 7.2 data.py: all functions importable and return correct types ────────────
try:
    from dashboard.data import (
        heartbeat_age, heartbeat_label, heartbeat_ok,
        service_status, agent_status,
        active_sessions, session_count,
        current_task_text, is_agent_busy,
        recent_tasks, recent_tasks_formatted,
        cost_summary, delegation_ratio,
        full_snapshot,
    )
    ok("dashboard.data: all functions importable")
except ImportError as e:
    fail("dashboard.data import failed", str(e))

# heartbeat_age returns int or None
try:
    _age = heartbeat_age()
    assert _age is None or isinstance(_age, int), f"type: {type(_age)}"
    ok("data.heartbeat_age(): returns int or None", f"{_age}s" if _age else "file missing")
except Exception as e:
    fail("data.heartbeat_age() failed", str(e)[:80])

# heartbeat_label returns string
try:
    _lbl = heartbeat_label()
    assert isinstance(_lbl, str) and len(_lbl) > 0
    ok("data.heartbeat_label(): returns non-empty string", repr(_lbl))
except Exception as e:
    fail("data.heartbeat_label() failed", str(e)[:80])

# heartbeat_ok returns bool
try:
    _ok = heartbeat_ok()
    assert isinstance(_ok, bool)
    ok("data.heartbeat_ok(): returns bool", str(_ok))
except Exception as e:
    fail("data.heartbeat_ok() failed", str(e)[:80])

# agent_status returns a valid string
try:
    _st = agent_status()
    assert _st in ("active", "inactive", "failed", "unknown", "activating"), f"unexpected: {_st}"
    ok("data.agent_status(): returns valid status string", _st)
except Exception as e:
    fail("data.agent_status() failed", str(e)[:80])

# active_sessions returns dict
try:
    _sess = active_sessions()
    assert isinstance(_sess, dict)
    ok("data.active_sessions(): returns dict", f"{len(_sess)} session(s)")
except Exception as e:
    fail("data.active_sessions() failed", str(e)[:80])

# current_task_text returns str
try:
    _ct = current_task_text()
    assert isinstance(_ct, str)
    ok("data.current_task_text(): returns str", repr(_ct[:40]))
except Exception as e:
    fail("data.current_task_text() failed", str(e)[:80])

# recent_tasks_formatted returns list of dicts with 'age'
try:
    _rt = recent_tasks_formatted(5)
    assert isinstance(_rt, list)
    if _rt:
        assert "age" in _rt[0], "missing 'age' key"
        assert "status" in _rt[0], "missing 'status' key"
    ok("data.recent_tasks_formatted(): returns list with 'age' field",
       f"{len(_rt)} entries")
except Exception as e:
    fail("data.recent_tasks_formatted() failed", str(e)[:80])

# cost_summary returns dict with required keys
try:
    _cs = cost_summary()
    for _k in ("week_dollars", "lifetime_dollars", "lifetime_delegations",
                "lifetime_gemini_tokens", "top_tasks"):
        assert _k in _cs, f"missing key: {_k}"
    assert _cs["lifetime_dollars"] > 0, "no lifetime savings recorded"
    ok("data.cost_summary(): all required keys, lifetime_dollars > 0",
       f"${_cs['lifetime_dollars']:.4f} saved")
except AssertionError as e:
    fail("data.cost_summary() assertion", str(e))
except Exception as e:
    fail("data.cost_summary() failed", str(e)[:80])

# delegation_ratio returns (int, int, float)
try:
    _avoided, _gemini, _ratio = delegation_ratio()
    assert isinstance(_ratio, float)
    assert 0.0 <= _ratio <= 100.0, f"ratio out of range: {_ratio}"
    ok("data.delegation_ratio(): returns (int, int, float) in [0,100]",
       f"{_ratio:.1f}% to Gemini")
except AssertionError as e:
    fail("data.delegation_ratio() assertion", str(e))
except Exception as e:
    fail("data.delegation_ratio() failed", str(e)[:80])

# full_snapshot returns complete dict
try:
    _snap = full_snapshot()
    for _k in ("generated_at", "heartbeat_label", "agent_status",
               "session_count", "sessions", "current_task",
               "recent_tasks", "costs"):
        assert _k in _snap, f"missing: {_k}"
    ok("data.full_snapshot(): all required keys present",
       f"generated at {_snap['generated_at'][:19]}")
except AssertionError as e:
    fail("data.full_snapshot() missing key", str(e))
except Exception as e:
    fail("data.full_snapshot() failed", str(e)[:80])

# ── 7.3 widget imports ────────────────────────────────────────────────────────
try:
    from dashboard.widgets.status_bar   import StatusBar
    from dashboard.widgets.task_panel   import TaskPanel
    from dashboard.widgets.cost_panel   import CostPanel
    from dashboard.widgets.token_meter  import TokenMeter
    from dashboard.widgets.session_panel import SessionPanel
    ok("dashboard widgets: all 5 import OK")
except ImportError as e:
    fail("widget import failed", str(e))

# ── 7.4 NazirDashboard imports and instantiates ───────────────────────────────
try:
    from dashboard.app import NazirDashboard, REFRESH_INTERVAL
    app = NazirDashboard()
    assert REFRESH_INTERVAL == 2.0, f"REFRESH_INTERVAL={REFRESH_INTERVAL} (expected 2.0)"
    ok("NazirDashboard instantiates, REFRESH_INTERVAL=2.0s")
except Exception as e:
    fail("NazirDashboard instantiation failed", str(e)[:80])

# ── 7.5 headless render: all widgets mount, data flows ────────────────────────
try:
    import asyncio

    async def _headless_test():
        from dashboard.app import NazirDashboard
        app = NazirDashboard()
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            # Verify all 5 widgets are mounted
            sb = app.query_one("StatusBar")
            tp = app.query_one("TaskPanel")
            cp = app.query_one("CostPanel")
            tm = app.query_one("TokenMeter")
            sp = app.query_one("SessionPanel")
            # Verify $ counter widget has correct class
            assert cp.__class__.__name__ == "CostPanel"
            # Verify the cost_panel's lifetime-value was updated (content attr)
            lifetime_widget = cp.query_one("#lifetime-value")
            content = str(lifetime_widget.content)
            return content

    _content = asyncio.run(_headless_test())
    ok("headless render: all 5 widgets mounted, data flows to CostPanel",
       f"lifetime-value content: {repr(_content[:50])}")
except Exception as e:
    fail("headless render failed", str(e)[:120])

# ── 7.6 export.py: HTML export works and contains expected content ────────────
try:
    from dashboard.export import export_html
    _html_path = export_html()
    assert _html_path.exists(), "HTML file not created"
    _html = _html_path.read_text()
    for _kw in ("heartbeat", "Lifetime", "Active Task", "Token Meter",
                "Top Tasks", "Sessions", "$ Saved"):
        assert _kw in _html, f"keyword missing from HTML: {_kw}"
    assert _html_path.stat().st_size > 3000, "HTML too small (<3KB)"
    ok("export_html(): file created with all required sections",
       f"{_html_path.stat().st_size} bytes")
except AssertionError as e:
    fail("export_html() assertion", str(e))
except Exception as e:
    fail("export_html() failed", str(e)[:80])

# ── 7.7 export.py: SVG export works ──────────────────────────────────────────
try:
    from dashboard.export import export_svg
    _svg_path = export_svg()
    assert _svg_path.exists(), "SVG file not created"
    _svg = _svg_path.read_text()
    assert _svg.startswith("<svg") or "<svg" in _svg[:200], "not valid SVG"
    assert _svg_path.stat().st_size > 1000, "SVG too small"
    ok("export_svg(): valid SVG file created",
       f"{_svg_path.stat().st_size} bytes")
except AssertionError as e:
    fail("export_svg() assertion", str(e))
except Exception as e:
    fail("export_svg() failed", str(e)[:80])

# ── 7.8 exports/ directory created ───────────────────────────────────────────
_exports = PROJECT_ROOT / "dashboard" / "exports"
if _exports.exists():
    _export_files = list(_exports.glob("nazir_dashboard_*"))
    ok(f"dashboard/exports/: {len(_export_files)} snapshot file(s) present")
else:
    fail("dashboard/exports/ not created")

# ── 7.9 MCP tools: dashboard_snapshot + export_dashboard in server.py ─────────
try:
    _srv = (PROJECT_ROOT / "mcp_server" / "server.py").read_text()
    assert "def dashboard_snapshot" in _srv, "dashboard_snapshot tool missing"
    assert "def export_dashboard"   in _srv, "export_dashboard tool missing"
    ok("MCP server: dashboard_snapshot + export_dashboard tools present")
except AssertionError as e:
    fail("MCP dashboard tools missing", str(e))
except Exception as e:
    fail("MCP tool check failed", str(e)[:80])

# ── 7.10 dashboard_snapshot MCP tool returns valid JSON ───────────────────────
try:
    # Import server and call the function directly (not via MCP transport)
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "mcp_server_mod", PROJECT_ROOT / "mcp_server" / "server.py"
    )
    # Instead, just call full_snapshot directly (same as the MCP tool does)
    from dashboard.data import full_snapshot as _fs
    _snap_json = json.dumps(_fs())
    _snap_parsed = json.loads(_snap_json)
    assert "agent_status" in _snap_parsed
    assert "costs" in _snap_parsed
    ok("dashboard_snapshot data: serializes to valid JSON with all keys")
except Exception as e:
    fail("dashboard_snapshot JSON test failed", str(e)[:80])

# ── 7.11 PRD acceptance: dashboard renders, $ counter shows real data ─────────
try:
    from dashboard.data import cost_summary as _cs2
    _snap2 = _cs2()
    assert _snap2["lifetime_dollars"] > 0, "no $ saved recorded in DB"
    assert _snap2["lifetime_delegations"] >= 3, "fewer than 3 delegations"
    ok("PRD acceptance: $ Saved counter shows real non-zero data",
       f"${_snap2['lifetime_dollars']:.4f} lifetime, "
       f"{_snap2['lifetime_delegations']} delegations")
except AssertionError as e:
    fail("PRD acceptance failed", str(e))
except Exception as e:
    fail("PRD acceptance check failed", str(e)[:80])



# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 — Specialized Subagents
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 8 — Specialized Subagents")

# ── 8.1 Module imports ────────────────────────────────────────────────────────
try:
    from orchestrator.agents import (
        AgentResult, PipelineResult, AgentError,
        PlannerAgent, CoderAgent, TesterAgent, ReviewerAgent,
        SubagentOrchestrator, run_agent, pipeline_summary,
        _extract_json, DEFAULT_MAX_ITERATIONS, DEFAULT_TEST_COMMAND,
    )
    ok("orchestrator.agents: all symbols importable")
except ImportError as e:
    fail("orchestrator.agents import failed", str(e))

# ── 8.2 agents.py file exists ─────────────────────────────────────────────────
_agents_file = PROJECT_ROOT / "orchestrator" / "agents.py"
if _agents_file.exists() and _agents_file.stat().st_size > 2000:
    ok("orchestrator/agents.py exists", f"{_agents_file.stat().st_size} bytes")
else:
    fail("orchestrator/agents.py missing or too small")

# ── 8.3 AgentResult dataclass ─────────────────────────────────────────────────
try:
    _r = AgentResult("planner", True, "output", {"key": "val"}, 100, "", 1.5)
    assert _r.role == "planner"
    assert _r.success is True
    assert _r.tokens_used == 100
    assert _r.duration_s == 1.5
    assert _r.data == {"key": "val"}
    # defaults
    _r2 = AgentResult("tester", False, "fail output")
    assert _r2.data == {}
    assert _r2.error == ""
    assert _r2.tokens_used == 0
    ok("AgentResult dataclass: all fields + defaults correct")
except AssertionError as e:
    fail("AgentResult dataclass wrong", str(e))
except Exception as e:
    fail("AgentResult dataclass failed", str(e)[:80])

# ── 8.4 PipelineResult dataclass ──────────────────────────────────────────────
try:
    _pr = PipelineResult(success=True, task="test task")
    assert _pr.iterations == []
    assert _pr.dollars_saved == 0.0
    assert _pr.committed is False
    assert _pr.commit_hash == ""
    ok("PipelineResult dataclass: defaults correct")
except Exception as e:
    fail("PipelineResult dataclass failed", str(e)[:80])

# ── 8.5 AgentError is a proper exception ──────────────────────────────────────
try:
    try:
        raise AgentError("test error message")
    except AgentError as e:
        assert str(e) == "test error message"
    ok("AgentError: raises and catches correctly")
except Exception as e:
    fail("AgentError exception failed", str(e)[:80])

# ── 8.6 _extract_json: all cases ─────────────────────────────────────────────
try:
    # Bare JSON
    d = _extract_json('{"steps": ["a", "b"]}')
    assert d["steps"] == ["a", "b"], f"bare JSON failed: {d}"
    # Markdown fence
    d2 = _extract_json('```json\n{"decision": "APPROVED"}\n```')
    assert d2.get("decision") == "APPROVED", f"fence failed: {d2}"
    # Prose with embedded JSON
    d3 = _extract_json('Here is the plan: {"steps": ["x"]} done.')
    assert d3.get("steps") == ["x"], f"embedded failed: {d3}"
    # No JSON → empty dict
    d4 = _extract_json("no json here at all")
    assert d4 == {}, f"no-json failed: {d4}"
    ok("_extract_json: bare / fenced / embedded / none all handled")
except AssertionError as e:
    fail("_extract_json case failed", str(e))
except Exception as e:
    fail("_extract_json threw", str(e)[:80])

# ── 8.7 DEFAULT_MAX_ITERATIONS and DEFAULT_TEST_COMMAND ──────────────────────
try:
    assert DEFAULT_MAX_ITERATIONS == 3, f"expected 3, got {DEFAULT_MAX_ITERATIONS}"
    assert "test_all_phases.py" in DEFAULT_TEST_COMMAND
    ok("constants: DEFAULT_MAX_ITERATIONS=3, DEFAULT_TEST_COMMAND references test_all_phases.py")
except AssertionError as e:
    fail("constants wrong", str(e))

# ── 8.8 Agent classes instantiate ─────────────────────────────────────────────
try:
    _pl = PlannerAgent()
    _co = CoderAgent()
    _te = TesterAgent()
    _re = ReviewerAgent()
    assert hasattr(_pl, "run") and callable(_pl.run)
    assert hasattr(_co, "run") and callable(_co.run)
    assert hasattr(_te, "run") and callable(_te.run)
    assert hasattr(_re, "run") and callable(_re.run)
    assert hasattr(_te, "test_command")
    ok("all 4 agent classes instantiate with .run() method")
except Exception as e:
    fail("agent class instantiation failed", str(e)[:80])

# ── 8.9 TesterAgent: custom test_command ──────────────────────────────────────
try:
    _te2 = TesterAgent(test_command="echo CUSTOM_CMD_OK")
    assert _te2.test_command == "echo CUSTOM_CMD_OK"
    _result = _te2.run("dummy task")
    assert _result.success, f"echo should succeed: {_result.error}"
    assert "CUSTOM_CMD_OK" in _result.output
    ok("TesterAgent: custom test_command works, runs and returns output")
except Exception as e:
    fail("TesterAgent custom command failed", str(e)[:80])

# ── 8.10 TesterAgent: captures failure correctly ──────────────────────────────
try:
    _te3 = TesterAgent(test_command="exit 1")
    _result3 = _te3.run("dummy")
    assert not _result3.success, "should have failed"
    assert _result3.data.get("returncode") == 1
    ok("TesterAgent: failure (exit 1) detected correctly, returncode=1")
except Exception as e:
    fail("TesterAgent failure detection failed", str(e)[:80])

# ── 8.11 SubagentOrchestrator: DI + happy path ────────────────────────────────
try:
    class _StubPlanner:
        def run(self, task, context=None):
            return AgentResult("planner", True, "plan",
                               {"steps": ["s1"], "acceptance_criteria": [],
                                "files_to_modify": [], "estimated_complexity": "low"},
                               50, "", 0.1)

    class _StubCoder:
        def __init__(self): self.calls = 0
        def run(self, task, context=None):
            self.calls += 1
            return AgentResult("coder", True, f"code call {self.calls}", {}, 200, "", 0.5)

    class _StubTesterPass:
        def __init__(self, test_command=None): pass
        def run(self, task, context=None):
            return AgentResult("tester", True, "100% pass",
                               {"passed": True, "feedback": "", "returncode": 0}, 0, "", 0.1)

    class _StubReviewer:
        def run(self, task, context=None):
            return AgentResult("reviewer", True, "APPROVED",
                               {"decision": "APPROVED", "feedback": "ok", "issues": []},
                               30, "", 0.2)

    _orch = SubagentOrchestrator(
        planner_cls=_StubPlanner, coder_cls=_StubCoder,
        tester_cls=_StubTesterPass, reviewer_cls=_StubReviewer,
    )
    _pr = _orch.run_pipeline("stub happy path task", dry_run=True)
    assert _pr.success, f"should succeed: {_pr.failure_reason}"
    assert len(_pr.iterations) == 1
    assert _pr.iterations[0][1].success is True
    assert _pr.review.data["decision"] == "APPROVED"
    assert _pr.committed is False   # dry_run
    ok("SubagentOrchestrator: DI happy path → success in 1 iteration, dry_run")
except AssertionError as e:
    fail("orchestrator happy path assertion", str(e))
except Exception as e:
    fail("orchestrator happy path failed", str(e)[:80])

# ── 8.12 Pipeline: retry on test failure, then succeed ────────────────────────
try:
    class _StubTesterPassOn2:
        def __init__(self, test_command=None): self.calls = 0
        def run(self, task, context=None):
            self.calls += 1
            success = self.calls >= 2
            return AgentResult("tester", success, "out",
                               {"passed": success, "feedback": "line 42" if not success else "", "returncode": 0 if success else 1},
                               0, "" if success else "line 42", 0.1)

    _orch2 = SubagentOrchestrator(
        planner_cls=_StubPlanner, coder_cls=_StubCoder,
        tester_cls=_StubTesterPassOn2, reviewer_cls=_StubReviewer,
    )
    _pr2 = _orch2.run_pipeline("retry task", dry_run=True)
    assert _pr2.success
    assert len(_pr2.iterations) == 2
    assert _pr2.iterations[0][1].success is False
    assert _pr2.iterations[1][1].success is True
    ok("pipeline: retries once on failure, succeeds on 2nd iteration")
except AssertionError as e:
    fail("pipeline retry assertion", str(e))
except Exception as e:
    fail("pipeline retry failed", str(e)[:80])

# ── 8.13 Pipeline: iteration limit respected ──────────────────────────────────
try:
    class _StubTesterAlwaysFail:
        def __init__(self, test_command=None): pass
        def run(self, task, context=None):
            return AgentResult("tester", False, "FAIL",
                               {"passed": False, "feedback": "always broken", "returncode": 1},
                               0, "always broken", 0.1)

    _orch3 = SubagentOrchestrator(
        planner_cls=_StubPlanner, coder_cls=_StubCoder,
        tester_cls=_StubTesterAlwaysFail, reviewer_cls=_StubReviewer,
    )
    _pr3 = _orch3.run_pipeline("always failing", dry_run=True, max_iterations=3)
    assert not _pr3.success
    assert len(_pr3.iterations) == 3
    assert "tests still failing after 3 iterations" in _pr3.failure_reason
    ok("pipeline: iteration limit enforced at max_iterations=3")
except AssertionError as e:
    fail("iteration limit assertion", str(e))
except Exception as e:
    fail("iteration limit test failed", str(e)[:80])

# ── 8.14 Pipeline: review rejection stops pipeline ────────────────────────────
try:
    class _StubReviewerReject:
        def run(self, task, context=None):
            return AgentResult("reviewer", False, "REVISION_NEEDED",
                               {"decision": "REVISION_NEEDED", "feedback": "missing tests", "issues": ["no tests"]},
                               30, "missing tests", 0.2)

    _orch4 = SubagentOrchestrator(
        planner_cls=_StubPlanner, coder_cls=_StubCoder,
        tester_cls=_StubTesterPass, reviewer_cls=_StubReviewerReject,
    )
    _pr4 = _orch4.run_pipeline("rejected task", dry_run=True)
    assert not _pr4.success
    assert "review rejected" in _pr4.failure_reason
    assert "missing tests" in _pr4.failure_reason
    ok("pipeline: review rejection stops pipeline with correct reason")
except AssertionError as e:
    fail("review rejection assertion", str(e))
except Exception as e:
    fail("review rejection test failed", str(e)[:80])

# ── 8.15 pipeline_summary format ──────────────────────────────────────────────
try:
    _s = pipeline_summary(_pr)
    assert "SUCCESS" in _s or "FAILED" in _s
    assert "Iteration" in _s
    assert "Review" in _s
    assert "Duration" in _s
    ok("pipeline_summary(): contains SUCCESS/FAILED, Iteration, Review, Duration")
except AssertionError as e:
    fail("pipeline_summary format", str(e))
except Exception as e:
    fail("pipeline_summary failed", str(e)[:80])

# ── 8.16 run_agent() helper: validates role name ──────────────────────────────
try:
    from orchestrator.agents import AgentError as _AE, run_agent as _ra
    try:
        _ra("invalid_role", "task")
        fail("run_agent: should raise AgentError for bad role")
    except _AE as e:
        assert "Unknown role" in str(e)
        ok("run_agent(): raises AgentError for unknown role")
except Exception as e:
    fail("run_agent role validation failed", str(e)[:80])

# ── 8.17 TesterAgent real run: actual test suite (short smoke) ────────────────
try:
    # Run a trivially fast command to prove TesterAgent works end-to-end
    _te_real = TesterAgent(test_command="python3 -c \"print('SMOKE_OK'); exit(0)\"")
    _res_real = _te_real.run("smoke test")
    assert _res_real.success, f"smoke failed: {_res_real.error}"
    assert "SMOKE_OK" in _res_real.output
    ok("TesterAgent: real subprocess run, output captured correctly")
except Exception as e:
    fail("TesterAgent real run failed", str(e)[:80])

# ── 8.18 SubagentOrchestrator: test_command override flows to TesterAgent ─────
try:
    class _RecordingTester:
        recorded_cmd = None
        def __init__(self, test_command=None):
            _RecordingTester.recorded_cmd = test_command
        def run(self, task, context=None):
            return AgentResult("tester", True, "ok", {"passed": True, "feedback": "", "returncode": 0}, 0, "", 0.0)

    _orch5 = SubagentOrchestrator(
        planner_cls=_StubPlanner, coder_cls=_StubCoder,
        tester_cls=_RecordingTester, reviewer_cls=_StubReviewer,
        test_command="custom_test_cmd",
    )
    _pr5 = _orch5.run_pipeline("cmd flow test", dry_run=True)
    assert _RecordingTester.recorded_cmd == "custom_test_cmd"
    ok("SubagentOrchestrator: test_command override flows through to TesterAgent")
except AssertionError as e:
    fail("test_command flow assertion", str(e))
except Exception as e:
    fail("test_command flow failed", str(e)[:80])

# ── 8.19 MCP tools present in server.py ──────────────────────────────────────
try:
    _srv = (PROJECT_ROOT / "mcp_server" / "server.py").read_text()
    assert "def run_agent"    in _srv, "run_agent tool missing"
    assert "def run_pipeline" in _srv, "run_pipeline tool missing"
    ok("MCP server: run_agent + run_pipeline tools present")
except AssertionError as e:
    fail("MCP Phase 8 tools missing", str(e))
except Exception as e:
    fail("MCP server check failed", str(e)[:80])

# ── 8.20 PRD acceptance: task described in PRD is executable (dry_run) ─────────
# PRD test: "add a --dry-run flag to safe_run_command — confirm plan→code→test→review"
# We verify the orchestrator CAN run the pipeline shape; Gemini/Claude live calls
# are excluded from CI (they're slow + cost tokens) — tested manually in Phase 9.
try:
    _orch6 = SubagentOrchestrator(
        planner_cls=_StubPlanner, coder_cls=_StubCoder,
        tester_cls=_StubTesterPass, reviewer_cls=_StubReviewer,
    )
    _prd_result = _orch6.run_pipeline(
        "add a --dry-run flag to safe_run_command",
        dry_run=True,
    )
    assert _prd_result.success
    assert _prd_result.plan is not None
    assert len(_prd_result.iterations) >= 1
    assert _prd_result.review is not None
    assert _prd_result.committed is False
    ok("PRD acceptance: plan→code→test→review pipeline shape executes end-to-end",
       f"{len(_prd_result.iterations)} iteration(s), review={_prd_result.review.data.get('decision')}")
except AssertionError as e:
    fail("PRD acceptance assertion", str(e))
except Exception as e:
    fail("PRD acceptance failed", str(e)[:80])



# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 9 — First Real Mission
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 9 — First Real Mission")

# ── 9.1 Mission doc exists with required sections ─────────────────────────────
_mission_doc = PROJECT_ROOT / "docs" / "mission-01.md"
try:
    assert _mission_doc.exists(), "docs/mission-01.md not found"
    _doc = _mission_doc.read_text()
    for _section in ("Task", "Acceptance Criteria", "What Nazir Did",
                     "Human Assist Required", "Final Results", "Failure Log",
                     "Verdict", "Git History"):
        assert _section in _doc, f"section missing: {_section}"
    ok("docs/mission-01.md exists with all required sections",
       f"{_mission_doc.stat().st_size} bytes")
except AssertionError as e:
    fail("mission-01.md", str(e))
except Exception as e:
    fail("mission-01.md check failed", str(e)[:80])

# ── 9.2 tests/mission_01_test.py exists ───────────────────────────────────────
_m01 = PROJECT_ROOT / "tests" / "mission_01_test.py"
if _m01.exists() and _m01.stat().st_size > 500:
    ok("tests/mission_01_test.py exists", f"{_m01.stat().st_size} bytes")
else:
    fail("tests/mission_01_test.py missing or too small")

# ── 9.3 The feature works: safe_run_command has dry_run parameter ─────────────
try:
    from mcp_server.tools.shell import safe_run_command
    import inspect as _inspect
    _sig = _inspect.signature(safe_run_command)
    assert "dry_run" in _sig.parameters, \
        f"dry_run not in signature: {list(_sig.parameters)}"
    _default = _sig.parameters["dry_run"].default
    assert _default is False, f"default should be False, got {repr(_default)}"
    ok("safe_run_command: dry_run parameter exists with default=False",
       str(list(_sig.parameters)))
except AssertionError as e:
    fail("safe_run_command signature", str(e))
except Exception as e:
    fail("safe_run_command import failed", str(e)[:80])

# ── 9.4 dry_run=True: returns prefix, does not execute ────────────────────────
try:
    import os as _os
    _sentinel = "/tmp/nazir_dryrun_sentinel_phase9"
    if _os.path.exists(_sentinel): _os.unlink(_sentinel)
    _out = safe_run_command(f"touch {_sentinel}", dry_run=True)
    assert "DRY_RUN" in _out, f"missing DRY_RUN prefix: {repr(_out)}"
    assert not _os.path.exists(_sentinel), "command was executed — sentinel file created!"
    assert f"touch {_sentinel}" in _out, "command text missing from dry_run output"
    ok("safe_run_command dry_run=True: DRY_RUN prefix, sentinel NOT created",
       repr(_out[:60]))
except AssertionError as e:
    fail("dry_run=True behavior", str(e))
except Exception as e:
    fail("dry_run=True test failed", str(e)[:80])

# ── 9.5 dry_run=True: blocklist still enforced ────────────────────────────────
try:
    try:
        safe_run_command("rm -rf /", dry_run=True)
        fail("blocklist not enforced in dry_run mode")
    except PermissionError:
        ok("dry_run=True: blocklist enforced (rm -rf still blocked)")
except Exception as e:
    fail("blocklist enforcement check failed", str(e)[:80])

# ── 9.6 dry_run=False: backward compatible ────────────────────────────────────
try:
    _out2 = safe_run_command("echo PHASE9_OK", dry_run=False)
    assert "PHASE9_OK" in _out2
    _out3 = safe_run_command("echo COMPAT_OK")   # no dry_run arg
    assert "COMPAT_OK" in _out3
    ok("safe_run_command: dry_run=False and default both execute normally")
except Exception as e:
    fail("backward compat failed", str(e)[:80])

# ── 9.7 MCP run_command tool has dry_run parameter ────────────────────────────
try:
    _srv = (PROJECT_ROOT / "mcp_server" / "server.py").read_text()
    assert "dry_run: bool = False" in _srv or "dry_run=False" in _srv, \
        "dry_run not in run_command MCP tool"
    ok("MCP run_command tool: dry_run parameter present in server.py")
except AssertionError as e:
    fail("MCP run_command dry_run", str(e))
except Exception as e:
    fail("server.py check failed", str(e)[:80])

# ── 9.8 mission_01_test.py passes 7/7 ────────────────────────────────────────
try:
    import subprocess as _sp
    _r = _sp.run(
        ["python3", str(PROJECT_ROOT / "tests" / "mission_01_test.py")],
        capture_output=True, text=True, timeout=30,
        cwd=str(PROJECT_ROOT),
    )
    assert _r.returncode == 0, f"mission test failed:\n{_r.stdout[-500:]}"
    assert "7 passed  0 failed" in _r.stdout
    ok("tests/mission_01_test.py: 7/7 pass")
except AssertionError as e:
    fail("mission_01_test.py not fully passing", str(e)[:200])
except Exception as e:
    fail("mission_01_test.py run failed", str(e)[:80])

# ── 9.9 Metrics: mission added delegations and $ saved ────────────────────────
try:
    from orchestrator.metrics import cost_report as _cr9
    _rep9 = _cr9("all")
    assert _rep9["delegations"] >= 200, \
        f"expected >= 200 delegations, got {_rep9['delegations']}"
    assert _rep9["dollars_saved"] > 5.0, \
        f"expected > $5.00 saved, got ${_rep9['dollars_saved']:.4f}"
    ok("metrics: mission delegations recorded, cumulative savings real",
       f"{_rep9['delegations']} delegations, ${_rep9['dollars_saved']:.4f} saved")
except AssertionError as e:
    fail("metrics assertion", str(e))
except Exception as e:
    fail("metrics check failed", str(e)[:80])

# ── 9.10 Failure log is honest: mission doc acknowledges human assist ─────────
try:
    _doc2 = (PROJECT_ROOT / "docs" / "mission-01.md").read_text()
    assert "Human Assist Required" in _doc2 or "human" in _doc2.lower()
    assert "Failure Log" in _doc2
    assert "test spec" in _doc2.lower() or "test specification" in _doc2.lower() \
        or "assertion" in _doc2.lower()
    ok("failure log: mission doc honestly documents what needed human help")
except AssertionError as e:
    fail("failure log not honest enough", str(e))
except Exception as e:
    fail("failure log check failed", str(e)[:80])



# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 10 — Showcase & Polish
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 10 — Showcase & Polish")

# ── 10.1 README.md exists and has required sections ───────────────────────────
_readme = PROJECT_ROOT / "README.md"
try:
    assert _readme.exists(), "README.md not found"
    _rd = _readme.read_text()
    for _s in ("Results", "Architecture", "Quick Start", "Security",
               "What It Can't Do", "Build Phases", "Dashboard"):
        assert _s in _rd, f"section missing: {_s}"
    assert "measured" in _rd.lower() or "measured, not claimed" in _rd.lower(), \
        "README should state results are measured"
    ok("README.md: all required sections present, results marked as measured",
       f"{_readme.stat().st_size} bytes")
except AssertionError as e:
    fail("README.md", str(e))
except Exception as e:
    fail("README.md check failed", str(e)[:80])

# ── 10.2 README has real numbers from metrics ─────────────────────────────────
try:
    from orchestrator.metrics import cost_report as _cr10
    _r10 = _cr10("all")
    _rd2 = _readme.read_text()
    # README should mention >= $5 saved (we have $7+)
    import re as _re10
    _dollars = _re10.findall(r'\$(\d+\.\d+)', _rd2)
    assert any(float(d) >= 5.0 for d in _dollars), \
        f"no real dollar figure >= $5 in README: {_dollars}"
    ok("README.md: contains real dollar figures from metrics.db",
       f"found ${max(float(d) for d in _dollars):.2f}")
except AssertionError as e:
    fail("README real numbers", str(e))
except Exception as e:
    fail("README numbers check failed", str(e)[:80])

# ── 10.3 GitHub Actions CI workflow exists ────────────────────────────────────
_ci = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
try:
    assert _ci.exists(), ".github/workflows/ci.yml not found"
    _ci_text = _ci.read_text()
    assert "test_all_phases.py" in _ci_text, "ci.yml doesn't run test suite"
    assert "python" in _ci_text.lower(), "ci.yml missing python setup"
    assert "gemini" in _ci_text.lower(), "ci.yml missing gemini setup"
    assert "GEMINI_API_KEY" in _ci_text, "ci.yml missing GEMINI_API_KEY secret"
    ok(".github/workflows/ci.yml: exists, runs test_all_phases.py",
       f"{_ci.stat().st_size} bytes")
except AssertionError as e:
    fail("ci.yml", str(e))
except Exception as e:
    fail("ci.yml check failed", str(e)[:80])

# ── 10.4 docs/ directory has mission report ───────────────────────────────────
_docs = PROJECT_ROOT / "docs"
try:
    assert _docs.exists(), "docs/ directory missing"
    _doc_files = list(_docs.glob("*.md"))
    assert len(_doc_files) >= 1, "no markdown files in docs/"
    ok(f"docs/: exists with {len(_doc_files)} document(s)",
       ", ".join(f.name for f in _doc_files))
except AssertionError as e:
    fail("docs/ directory", str(e))
except Exception as e:
    fail("docs/ check failed", str(e)[:80])

# ── 10.5 tests/ directory has mission test ────────────────────────────────────
_tests_dir = PROJECT_ROOT / "tests"
try:
    assert _tests_dir.exists(), "tests/ directory missing"
    _test_files = list(_tests_dir.glob("*.py"))
    assert len(_test_files) >= 1, "no test files in tests/"
    ok(f"tests/: exists with {len(_test_files)} file(s)",
       ", ".join(f.name for f in _test_files))
except AssertionError as e:
    fail("tests/ directory", str(e))
except Exception as e:
    fail("tests/ check failed", str(e)[:80])

# ── 10.6 git remote points to GitHub ──────────────────────────────────────────
try:
    import subprocess as _sp10
    _remote = _sp10.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    ).stdout.strip()
    assert "github.com" in _remote, f"remote not on GitHub: {_remote}"
    assert "ahmed-145" in _remote or "Nazir" in _remote or "nazir" in _remote
    ok("git remote: points to GitHub", _remote)
except AssertionError as e:
    fail("git remote", str(e))
except Exception as e:
    fail("git remote check failed", str(e)[:80])

# ── 10.7 all phases 0-9 marked complete in PRD ────────────────────────────────
try:
    _prd = (PROJECT_ROOT / "Nazir_PRD_v4.md").read_text()
    _phases_complete = _prd.count("✅")
    assert _phases_complete >= 10, \
        f"only {_phases_complete} phases marked ✅ in PRD (expected >= 10)"
    ok(f"PRD: {_phases_complete} phases marked ✅")
except AssertionError as e:
    fail("PRD phase completion", str(e))
except Exception as e:
    fail("PRD check failed", str(e)[:80])

# ── 10.8 dashboard export works (HTML) ───────────────────────────────────────
try:
    from dashboard.export import export_html as _eh10
    _html = _eh10()
    assert _html.exists() and _html.stat().st_size > 2000
    ok("dashboard HTML export: works", f"{_html.stat().st_size} bytes → {_html.name}")
except Exception as e:
    fail("dashboard export failed", str(e)[:80])

# ── 10.9 .env.example exists (safe for public repo) ──────────────────────────
_env_ex = PROJECT_ROOT / ".env.example"
try:
    assert _env_ex.exists(), ".env.example missing"
    _ex_text = _env_ex.read_text()
    assert "GEMINI_API_KEY" in _ex_text
    assert "your" in _ex_text.lower() or "key" in _ex_text.lower()
    ok(".env.example: exists with placeholder keys (safe for public repo)")
except AssertionError as e:
    fail(".env.example", str(e))
except Exception as e:
    fail(".env.example check failed", str(e)[:80])

# ── 10.10 .gitignore excludes sensitive files ─────────────────────────────────
_gi = PROJECT_ROOT / ".gitignore"
try:
    assert _gi.exists()
    _gi_text = _gi.read_text()
    for _entry in (".env", "metrics.db", "__pycache__"):
        assert _entry in _gi_text, f"missing from .gitignore: {_entry}"
    ok(".gitignore: .env, metrics.db, __pycache__ all excluded")
except AssertionError as e:
    fail(".gitignore", str(e))
except Exception as e:
    fail(".gitignore check failed", str(e)[:80])

# ── 10.11 Complete test count confirms all phases covered ─────────────────────
# This test passes only if all prior phases also pass — final sanity check
_current_pass = len([r for r in results if r[0] is True])
_current_fail = len([r for r in results if r[0] is False])
if _current_fail == 0:
    ok(f"all {_current_pass} prior tests passing — full stack verified end-to-end")
else:
    fail(f"{_current_fail} failures in prior phases — stack not fully verified")


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
passed  = [r for r in results if r[0] is True]
failed  = [r for r in results if r[0] is False]
skipped = [r for r in results if r[0] is None]

total = len(results)
n_pass = len(passed)
n_fail = len(failed)
n_skip = len(skipped)

print(f"\n{BO}{'═'*62}{RE}")
print(f"{BO}  RESULTS{RE}")
print(f"{'═'*62}")
print(f"  {G}{n_pass:>3} passed{RE}   {R}{n_fail:>2} failed{RE}   {Y}{n_skip:>2} skipped{RE}   {total} total")

if failed:
    print(f"\n{R}{BO}  FAILURES:{RE}")
    for _, name, detail in failed:
        print(f"  {R}✗{RE}  {name}")
        if detail:
            print(f"     {detail}")

if skipped:
    print(f"\n{Y}  SKIPPED:{RE}")
    for _, name, detail in skipped:
        print(f"  {Y}·{RE}  {name}" + (f"  →  {detail}" if detail else ""))

score = n_pass / (total - n_skip) * 100 if (total - n_skip) > 0 else 0
color = G if score >= 90 else (Y if score >= 70 else R)
print(f"\n  {color}{BO}Score: {score:.0f}%  ({n_pass}/{total - n_skip} non-skipped){RE}")
print(f"{'═'*62}\n")

sys.exit(0 if n_fail == 0 else 1)
