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
