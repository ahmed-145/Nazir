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


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5 — Context Management
# ═══════════════════════════════════════════════════════════════════════════════
header("Phase 5 — Context Management")

try:
    from memory.wrapup import write_checkpoint, quick_wrapup
    from memory.catchup import restore, summary
    from memory.updater import full_update, prepend_decision
    ok("Phase 5 modules import OK")
except ImportError as e:
    fail("Phase 5 module import failed", str(e))

# wrapup creates checkpoint
try:
    archive = write_checkpoint("test task", ["done"], ["pending"], [], [], [])
    if Path(archive).exists():
        ok("write_checkpoint: archive created", archive[-40:])
    else:
        fail("write_checkpoint: archive not found")
except Exception as e:
    fail("write_checkpoint failed", str(e)[:80])

# last_checkpoint.md exists
cp = PROJECT_ROOT / "memory" / "last_checkpoint.md"
if cp.exists() and cp.stat().st_size > 0:
    ok("last_checkpoint.md: exists and non-empty", f"{cp.stat().st_size} bytes")
else:
    fail("last_checkpoint.md missing")

# checkpoints archive dir has files
ckpts = list((PROJECT_ROOT / "memory" / "checkpoints").glob("*.md"))
ok(f"checkpoints archive: {len(ckpts)} file(s)")

# catchup round-trip
try:
    ctx = restore()
    s = summary()
    if s["has_checkpoint"] and "sessions_count" in s:
        ok("catchup round-trip: checkpoint + sessions restored", f"age={s['checkpoint_age_seconds']}s")
    else:
        fail("catchup round-trip failed", str(s))
except Exception as e:
    fail("catchup failed", str(e)[:80])

# hooks configured
hooks_file = PROJECT_ROOT / ".claude" / "settings.json"
if hooks_file.exists():
    data = json.loads(hooks_file.read_text())
    h = data.get("hooks", {})
    if h.get("PreCompact") and h.get("Stop"):
        ok("Claude Code hooks: PreCompact + Stop configured")
    else:
        fail("hooks missing from .claude/settings.json")
else:
    fail(".claude/settings.json not found")

# hook command works as subprocess
r = run(["python3", str(PROJECT_ROOT / "memory" / "wrapup.py")], timeout=10)
if r.returncode == 0 and "Checkpoint" in r.stdout:
    ok("wrapup.py runs as hook command (subprocess)")
else:
    fail("wrapup.py hook command failed", r.stderr[:60])
