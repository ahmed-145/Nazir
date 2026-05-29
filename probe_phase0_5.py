#!/usr/bin/env python3
"""
Phase 0.5 — Assumption Probe
Run this BEFORE writing any Phase 1+ code.
It empirically tests every load-bearing assumption the PRD makes about
Gemini CLI, Antigravity 2.0 CLI, and Claude Code headless mode.
Results saved to memory/probe_results.json and memory/probe_report.md.

Usage:
    python3 probe_phase0_5.py

Requirements:
    - GOOGLE_API_KEY must be set (for Gemini CLI tests)
    - gemini CLI must be installed and on PATH
    - python 3.10+
    - No network calls beyond what the CLIs make themselves
"""

import subprocess
import json
import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
RESULTS_FILE = PROJECT_ROOT / "memory" / "probe_results.json"
REPORT_FILE = PROJECT_ROOT / "memory" / "probe_report.md"
PROBE_TMPDIR = PROJECT_ROOT / "memory" / "_probe_tmp"

results = {}

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def header(title):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}")


def ok(label, detail=""):
    mark = f"{GREEN}PASS{RESET}"
    print(f"  {mark}  {label}" + (f"  →  {detail}" if detail else ""))


def fail(label, detail=""):
    mark = f"{RED}FAIL{RESET}"
    print(f"  {mark}  {label}" + (f"  →  {detail}" if detail else ""))


def warn(label, detail=""):
    mark = f"{YELLOW}WARN{RESET}"
    print(f"  {mark}  {label}" + (f"  →  {detail}" if detail else ""))


def run(cmd, timeout=30, env=None):
    """Run a command, return (returncode, stdout, stderr)."""
    merged_env = {**os.environ, **(env or {})}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, env=merged_env
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError:
        return -2, "", "NOT_FOUND"


# ─────────────────────────────────────────────────────────────
# SECTION 1: Prerequisites
# ─────────────────────────────────────────────────────────────
header("1 · Prerequisites")

PROBE_TMPDIR.mkdir(parents=True, exist_ok=True)

# 1.1 GOOGLE_API_KEY
has_key = bool(os.environ.get("GOOGLE_API_KEY"))
results["google_api_key_set"] = has_key
if has_key:
    ok("GOOGLE_API_KEY is set")
else:
    fail("GOOGLE_API_KEY not set — Gemini tests will be skipped")

# 1.2 gemini CLI on PATH
rc, stdout, _ = run(["gemini", "--version"])
gemini_available = rc == 0
results["gemini_cli_available"] = gemini_available
results["gemini_cli_version"] = stdout.strip() if gemini_available else None
if gemini_available:
    ok("gemini CLI found", stdout.strip())
else:
    fail("gemini CLI not found on PATH")

# 1.3 antigravity CLI on PATH
rc, stdout, _ = run(["antigravity", "--version"])
ag_available = rc == 0
results["antigravity_cli_available"] = ag_available
results["antigravity_cli_version"] = stdout.strip() if ag_available else None
if ag_available:
    ok("antigravity CLI found (2.0+)", stdout.strip())
else:
    warn("antigravity CLI not found — Antigravity 2.0 tests will be skipped")
    print("       Install: https://antigravity.google/docs/cli")

# 1.4 claude CLI on PATH
rc, stdout, _ = run(["claude", "--version"])
claude_available = rc == 0
results["claude_cli_available"] = claude_available
results["claude_cli_version"] = stdout.strip() if claude_available else None
if claude_available:
    ok("claude CLI found", stdout.strip())
else:
    fail("claude CLI not found on PATH")


# ─────────────────────────────────────────────────────────────
# SECTION 2: Gemini CLI — Headless basics
# ─────────────────────────────────────────────────────────────
header("2 · Gemini CLI — Headless basics")

if not (gemini_available and has_key):
    warn("Skipping all Gemini tests (CLI unavailable or no API key)")
    results["gemini_tests_skipped"] = True
else:
    results["gemini_tests_skipped"] = False

    # 2.1 Basic headless -p with text output
    rc, stdout, stderr = run(
        ["gemini", "--yolo", "-p", "Reply with only the word: PROBE_OK"],
        timeout=30
    )
    passed = rc == 0 and "PROBE_OK" in stdout
    results["gemini_headless_basic"] = {"rc": rc, "passed": passed}
    if passed:
        ok("Basic headless -p works")
    else:
        fail("Basic headless -p failed", f"rc={rc} stderr={stderr[:120]}")

    # 2.2 --output-format json
    rc, stdout, stderr = run(
        ["gemini", "--yolo", "--output-format", "json", "-p",
         "Reply with only the word: PROBE_OK"],
        timeout=30
    )
    json_output = None
    json_parse_ok = False
    if rc == 0 and stdout.strip():
        try:
            json_output = json.loads(stdout)
            json_parse_ok = True
        except json.JSONDecodeError:
            pass

    results["gemini_json_output"] = {
        "rc": rc,
        "json_parse_ok": json_parse_ok,
        "keys": list(json_output.keys()) if json_output else [],
        "raw_preview": stdout[:300]
    }
    if json_parse_ok:
        ok("--output-format json parses cleanly", f"keys: {list(json_output.keys())}")
    elif rc == 0:
        warn("--output-format json: response is not valid JSON", stdout[:120])
    else:
        fail("--output-format json failed", f"rc={rc}")

    # 2.3 Does JSON output contain a sessionId? (PRD Issue #14435)
    session_id_in_json = False
    session_id_value = None
    if json_output:
        # Check common field names
        for key in ("sessionId", "session_id", "id", "session", "conversationId"):
            if key in json_output:
                session_id_in_json = True
                session_id_value = json_output[key]
                break

    results["gemini_json_has_session_id"] = {
        "found": session_id_in_json,
        "value": session_id_value,
        "all_keys": list(json_output.keys()) if json_output else []
    }
    if session_id_in_json:
        ok("JSON output DOES contain sessionId", f"{session_id_value}")
        print(f"       {GREEN}Issue #14435 is RESOLVED — resume round-trip is possible{RESET}")
    else:
        fail("JSON output does NOT contain sessionId (GitHub issue #14435 still open)")
        print(f"       {YELLOW}Your gemini_runner.py resume logic will break.{RESET}")
        print(f"       {YELLOW}Workaround: scrape session UUID from ~/.gemini/sessions/ after each call.{RESET}")

    # 2.4 Locate sessions directory & find latest session UUID (workaround path)
    sessions_dirs = list(Path.home().glob(".gemini/sessions/*/"))
    results["gemini_sessions_dir_exists"] = len(sessions_dirs) > 0
    results["gemini_sessions_dirs"] = [str(d) for d in sessions_dirs]
    if sessions_dirs:
        ok(f"Found {len(sessions_dirs)} session dir(s) under ~/.gemini/sessions/")
        # Find the most recently modified .jsonl
        jsonl_files = list(Path.home().glob(".gemini/sessions/**/*.jsonl"))
        results["gemini_session_files_count"] = len(jsonl_files)
        if jsonl_files:
            latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)
            results["gemini_latest_session_file"] = str(latest)
            results["gemini_latest_session_uuid"] = latest.stem
            ok(f"Latest session UUID (from filesystem)", latest.stem)
        else:
            warn("No .jsonl session files found yet (may appear after first real session)")
    else:
        warn("~/.gemini/sessions/ not found — sessions may be stored differently on this version")

    # 2.5 --resume with a known UUID (round-trip test)
    # Use the latest session UUID we found, or skip
    if results.get("gemini_latest_session_uuid"):
        uuid = results["gemini_latest_session_uuid"]
        rc, stdout, stderr = run(
            ["gemini", "--yolo", "--output-format", "json",
             "--resume", uuid, "-p", "Reply with only: RESUME_OK"],
            timeout=30
        )
        passed = rc == 0 and "RESUME_OK" in stdout
        results["gemini_resume_works"] = {"rc": rc, "passed": passed, "uuid_used": uuid}
        if passed:
            ok("--resume <uuid> works in headless mode", uuid[:16] + "...")
        else:
            fail("--resume <uuid> failed in headless mode", f"rc={rc} stderr={stderr[:120]}")
    else:
        results["gemini_resume_works"] = {"skipped": True, "reason": "no session UUID available"}
        warn("Skipping --resume test (no prior session UUID found)")
        print("       Run one real Gemini task first, then re-run probe.")

    # 2.6 Exit code on auth failure (test with bad key)
    rc, stdout, stderr = run(
        ["gemini", "--yolo", "-p", "say hi"],
        timeout=10,
        env={"GOOGLE_API_KEY": "invalid-key-probe-test"}
    )
    results["gemini_bad_key_exit_code"] = rc
    if rc == 41:
        ok("Exit code 41 = auth failure (PRD claim confirmed)", f"rc={rc}")
    elif rc != 0:
        warn(f"Auth failure returns rc={rc}, not 41 (PRD says 41)", f"stderr={stderr[:100]}")
    else:
        warn("Bad API key returned rc=0 (unexpected)", "may have used cached session")

    # 2.7 --yolo flag (just confirm it doesn't error)
    rc, stdout, stderr = run(
        ["gemini", "--yolo", "-p", "Reply with: YOLO_OK"],
        timeout=30
    )
    results["gemini_yolo_flag"] = {"rc": rc, "passed": rc == 0 and "YOLO_OK" in stdout}
    if results["gemini_yolo_flag"]["passed"]:
        ok("--yolo flag accepted and works")
    else:
        fail("--yolo flag failed", f"rc={rc}")

    # 2.8 Quota check via /stats (if supported)
    rc, stdout, stderr = run(
        ["gemini", "--output-format", "json", "-p", "/stats"],
        timeout=20
    )
    results["gemini_stats_command"] = {"rc": rc, "output_preview": stdout[:200]}
    if rc == 0 and stdout.strip():
        ok("/stats command works")
        try:
            stats_json = json.loads(stdout)
            results["gemini_stats_json"] = stats_json
            ok("  /stats returns parseable JSON", str(list(stats_json.keys())))
        except json.JSONDecodeError:
            warn("  /stats output is not JSON (may be plain text)")
    else:
        warn("/stats command failed or unavailable", f"rc={rc}")


# ─────────────────────────────────────────────────────────────
# SECTION 3: Gemini CLI — Policy engine TOML
# ─────────────────────────────────────────────────────────────
header("3 · Gemini CLI — Policy engine")

if gemini_available and has_key:
    policy_dir = Path.home() / ".gemini" / "policies"
    results["gemini_policy_dir_exists"] = policy_dir.exists()

    if policy_dir.exists():
        ok("~/.gemini/policies/ directory exists")
        toml_files = list(policy_dir.glob("*.toml"))
        results["gemini_policy_files"] = [str(f) for f in toml_files]
        if toml_files:
            ok(f"Found {len(toml_files)} policy TOML file(s)", str(toml_files))
        else:
            warn("No .toml files in ~/.gemini/policies/ (policy engine not configured yet)")
    else:
        warn("~/.gemini/policies/ does not exist yet")
        print("       Create it and add safe-commands.toml per Section 4.4 of PRD.")

    # Test: write a temp block policy and see if gemini respects it
    # We write a policy that blocks "echo" and try to run it
    test_policy_dir = PROBE_TMPDIR / "policies"
    test_policy_dir.mkdir(parents=True, exist_ok=True)
    test_policy = test_policy_dir / "probe-block.toml"
    test_policy.write_text("""
[[rules]]
priority = 999
tool = "run_shell_command"
prefix = "echo BLOCKED_PROBE"
decision = "block"
""")
    # We can't easily override the policy dir path per-invocation without knowing
    # the env var, so we just document that the policy dir exists and TOML is real
    results["gemini_policy_engine_toml_format_real"] = True
    ok("Policy engine TOML format is real (confirmed via official docs)")
    warn("Live policy enforcement test skipped (can't override policy dir per-invocation)")
    print("       To verify: add a block rule manually, restart gemini, run a blocked command.")
else:
    warn("Skipping policy tests")


# ─────────────────────────────────────────────────────────────
# SECTION 4: Gemini CLI — contextFileName setting
# ─────────────────────────────────────────────────────────────
header("4 · Gemini CLI — settings.json / contextFileName")

gemini_settings = Path.home() / ".gemini" / "settings.json"
results["gemini_settings_file_exists"] = gemini_settings.exists()

if gemini_settings.exists():
    try:
        settings_data = json.loads(gemini_settings.read_text())
        results["gemini_settings_keys"] = list(settings_data.keys())
        context_file = settings_data.get("contextFileName")
        results["gemini_contextFileName"] = context_file
        ok("~/.gemini/settings.json exists", f"keys: {list(settings_data.keys())}")
        if context_file:
            ok(f"contextFileName is set to: {context_file}")
            if context_file == "CLAUDE.md":
                ok("contextFileName = CLAUDE.md ✓ (PRD requirement met)")
            else:
                warn(f"contextFileName = {context_file!r} (PRD wants 'CLAUDE.md')")
        else:
            warn("contextFileName not set in settings.json")
            print("       Add: \"contextFileName\": \"CLAUDE.md\" to ~/.gemini/settings.json")
        # Check telemetry
        telem = settings_data.get("telemetry", {})
        if isinstance(telem, dict) and telem.get("enabled") is False:
            ok("Telemetry disabled in settings.json")
        else:
            warn("Telemetry may not be disabled in settings.json")
            print("       Add: \"telemetry\": {\"enabled\": false, \"target\": \"local\"}")
    except json.JSONDecodeError:
        fail("~/.gemini/settings.json is not valid JSON")
else:
    warn("~/.gemini/settings.json does not exist")
    print("       Create it per Section 4.3 of PRD.")


# ─────────────────────────────────────────────────────────────
# SECTION 5: Antigravity 2.0 CLI
# ─────────────────────────────────────────────────────────────
header("5 · Antigravity 2.0 CLI")

if not ag_available:
    warn("antigravity CLI not installed — skipping all Antigravity tests")
    print("       This is the NEW official automation surface (I/O May 2026).")
    print("       Install and re-run probe to benchmark vs Gemini CLI.")
    results["antigravity_tests_skipped"] = True
else:
    results["antigravity_tests_skipped"] = False

    # 5.1 Basic headless call
    rc, stdout, stderr = run(
        ["antigravity", "run", "--prompt", "Reply with only: AG_PROBE_OK"],
        timeout=45
    )
    # Also try without subcommand in case syntax differs
    if rc != 0:
        rc, stdout, stderr = run(
            ["antigravity", "-p", "Reply with only: AG_PROBE_OK"],
            timeout=45
        )

    passed = rc == 0 and "AG_PROBE_OK" in stdout
    results["antigravity_headless_basic"] = {"rc": rc, "passed": passed}
    if passed:
        ok("Antigravity CLI headless call works")
    else:
        warn("Antigravity CLI headless call syntax unclear", f"rc={rc} stderr={stderr[:120]}")
        print("       Check: antigravity --help for correct headless syntax")

    # 5.2 JSON output format
    for flag in ["--output-format json", "--format json", "--json"]:
        parts = flag.split()
        rc, stdout, stderr = run(
            ["antigravity"] + parts + ["-p", "Reply with: AG_JSON_OK"],
            timeout=30
        )
        if rc == 0:
            try:
                data = json.loads(stdout)
                results["antigravity_json_flag"] = flag
                results["antigravity_json_keys"] = list(data.keys())
                ok(f"JSON output works with flag: {flag}", f"keys: {list(data.keys())}")

                # Does it expose session ID?
                for key in ("sessionId", "session_id", "id", "session"):
                    if key in data:
                        results["antigravity_has_session_id"] = True
                        results["antigravity_session_id_key"] = key
                        ok(f"JSON has session ID under key: {key}")
                        break
                else:
                    results["antigravity_has_session_id"] = False
                    warn("JSON doesn't expose session ID")
                break
            except json.JSONDecodeError:
                pass
    else:
        results["antigravity_json_flag"] = None
        warn("Could not find working JSON output flag for Antigravity CLI")

    # 5.3 Quota/limits check
    rc, stdout, stderr = run(["antigravity", "quota"], timeout=15)
    if rc != 0:
        rc, stdout, stderr = run(["antigravity", "limits"], timeout=15)
    results["antigravity_quota_check"] = {"rc": rc, "output": stdout[:300]}
    if rc == 0:
        ok("Quota/limits command available", stdout[:100])
    else:
        warn("No quota subcommand found in Antigravity CLI")


# ─────────────────────────────────────────────────────────────
# SECTION 6: Claude Code headless stability
# ─────────────────────────────────────────────────────────────
header("6 · Claude Code — headless -p stability")

if not claude_available:
    warn("claude CLI not found, skipping")
else:
    # 6.1 Does claude -p complete a minimal task without dying?
    test_file = PROBE_TMPDIR / "claude_probe_output.txt"
    rc, stdout, stderr = run(
        ["claude", "--dangerously-skip-permissions", "-p",
         f"Write the string 'CLAUDE_PROBE_OK' to the file {test_file}. Do nothing else."],
        timeout=60
    )
    file_written = test_file.exists() and "CLAUDE_PROBE_OK" in test_file.read_text() if test_file.exists() else False
    results["claude_headless_completes"] = {"rc": rc, "file_written": file_written}

    if file_written:
        ok("claude -p headless completes a file-write task")
    elif rc == 0:
        warn("claude -p returned 0 but didn't write the file (may have refused or misunderstood)")
    else:
        fail(f"claude -p headless failed", f"rc={rc} stderr={stderr[:120]}")

    # 6.2 Check for the SIGTERM bug on longer runs (heuristic — just time it)
    print("  Timing a 20-second idle to check for premature SIGTERM...")
    rc, stdout, stderr = run(
        ["claude", "--dangerously-skip-permissions", "-p",
         "Count from 1 to 20, one number per second. Reply DONE when finished."],
        timeout=90
    )
    survived = rc == 0 and "DONE" in stdout
    results["claude_headless_20s_survival"] = {"rc": rc, "survived": survived}
    if survived:
        ok("claude -p survives a ~20s task (no premature SIGTERM observed)")
    else:
        fail(f"claude -p died on longer task", f"rc={rc} (known bug #29642)")
        print(f"       {YELLOW}Use tmux or screen rather than systemd for daemon mode{RESET}")
        print(f"       Issue: https://github.com/anthropics/claude-code/issues/29642")


# ─────────────────────────────────────────────────────────────
# SECTION 7: Path / environment sanity
# ─────────────────────────────────────────────────────────────
header("7 · Path & environment sanity")

# 7.1 NAZIR_PROJECT_ROOT
project_root_env = os.environ.get("NAZIR_PROJECT_ROOT")
results["NAZIR_PROJECT_ROOT_set"] = bool(project_root_env)
if project_root_env:
    ok(f"NAZIR_PROJECT_ROOT = {project_root_env}")
else:
    warn("NAZIR_PROJECT_ROOT not set")
    print(f"       Add to ~/.bashrc: export NAZIR_PROJECT_ROOT='{PROJECT_ROOT}'")
    print(f"       This will fix every hardcoded path in systemd units and daemon code.")

# 7.2 .geminiignore
geminiignore = PROJECT_ROOT / ".geminiignore"
results[".geminiignore_exists"] = geminiignore.exists()
if geminiignore.exists():
    ok(".geminiignore exists (quota burn prevented)")
else:
    fail(".geminiignore MISSING — Gemini MemoryDiscovery will burn quota on startup")

# 7.3 .env
dotenv = PROJECT_ROOT / ".env"
results[".env_exists"] = dotenv.exists()
if dotenv.exists():
    content = dotenv.read_text()
    has_google_key = "GOOGLE_API_KEY" in content
    results[".env_has_google_key"] = has_google_key
    if has_google_key:
        ok(".env has GOOGLE_API_KEY")
    else:
        warn(".env exists but GOOGLE_API_KEY not found in it")
else:
    warn(".env not found")


# ─────────────────────────────────────────────────────────────
# SECTION 8: cgcone availability
# ─────────────────────────────────────────────────────────────
header("8 · cgcone / AgentLink")

rc, stdout, _ = run(["cgcone", "--version"])
cgcone_ok = rc == 0
results["cgcone_available"] = cgcone_ok
if cgcone_ok:
    ok("cgcone is installed", stdout.strip())
else:
    warn("cgcone not installed")
    print("       npm install -g cgcone")
    print("       Alternative: AgentLink (https://github.com/digimetalab/agentlink)")

rc, stdout, _ = run(["agentlink", "--version"])
results["agentlink_available"] = rc == 0
if rc == 0:
    ok("agentlink is installed (cgcone fallback)", stdout.strip())


# ─────────────────────────────────────────────────────────────
# SECTION 9: Antigravity 2.0 vs Gemini CLI — recommendation
# ─────────────────────────────────────────────────────────────
header("9 · Backend recommendation (based on probe results)")

ag_works = not results.get("antigravity_tests_skipped") and results.get("antigravity_headless_basic", {}).get("passed")
gemini_works = not results.get("gemini_tests_skipped") and results.get("gemini_headless_basic", {}).get("passed")
gemini_resume_works = results.get("gemini_resume_works", {}).get("passed", False)
session_id_available = (
    results.get("gemini_json_has_session_id", {}).get("found") or
    bool(results.get("gemini_latest_session_uuid"))
)

if ag_works and gemini_works:
    print(f"  {BOLD}Both backends work. Use Gemini CLI for bulk/analysis, Antigravity CLI for agent tasks.")
    print(f"  Antigravity has official automation blessing since I/O 2026.{RESET}")
    results["recommendation"] = "both"
elif gemini_works:
    print(f"  {BOLD}Use Gemini CLI as the execution backend. Antigravity CLI not available.{RESET}")
    results["recommendation"] = "gemini_cli_only"
    if not session_id_available:
        print(f"  {YELLOW}WARNING: Session resume may be unreliable (see #14435).{RESET}")
        print(f"  Workaround: scrape UUID from ~/.gemini/sessions/ filesystem after each call.")
elif ag_works:
    print(f"  {BOLD}Use Antigravity 2.0 CLI as primary backend. Gemini CLI unavailable.{RESET}")
    results["recommendation"] = "antigravity_cli_only"
else:
    print(f"  {RED}NEITHER backend available. Install gemini CLI or antigravity CLI before Phase 1.{RESET}")
    results["recommendation"] = "neither"


# ─────────────────────────────────────────────────────────────
# SAVE RESULTS
# ─────────────────────────────────────────────────────────────
header("Results saved")

results["probe_timestamp"] = datetime.now().isoformat()
results["probe_version"] = "0.5.0"

RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
RESULTS_FILE.write_text(json.dumps(results, indent=2))
ok(f"JSON results → {RESULTS_FILE}")

# Build markdown report
lines = [
    f"# Phase 0.5 Probe Report",
    f"Generated: {results['probe_timestamp']}",
    f"",
    f"## Summary",
    f"",
    f"| Check | Result |",
    f"|---|---|",
    f"| GOOGLE_API_KEY set | {'✅' if results.get('google_api_key_set') else '❌'} |",
    f"| gemini CLI available | {'✅' if results.get('gemini_cli_available') else '❌'} |",
    f"| gemini headless -p | {'✅' if results.get('gemini_headless_basic', {}).get('passed') else '❌'} |",
    f"| gemini --output-format json | {'✅' if results.get('gemini_json_output', {}).get('json_parse_ok') else '❌'} |",
    f"| JSON has sessionId (#14435) | {'✅ RESOLVED' if results.get('gemini_json_has_session_id', {}).get('found') else '❌ STILL OPEN'} |",
    f"| --resume works in headless | {'✅' if results.get('gemini_resume_works', {}).get('passed') else '⚠️ untested/failed'} |",
    f"| Exit code 41 = auth fail | {'✅' if results.get('gemini_bad_key_exit_code') == 41 else f'⚠️ actual={results.get(\"gemini_bad_key_exit_code\")}'} |",
    f"| Policy engine dir exists | {'✅' if results.get('gemini_policy_dir_exists') else '⚠️ not yet'} |",
    f"| settings.json contextFileName | {'✅' if results.get('gemini_contextFileName') == 'CLAUDE.md' else '⚠️ not set'} |",
    f"| Antigravity 2.0 CLI available | {'✅' if results.get('antigravity_cli_available') else '⚠️ not installed'} |",
    f"| Antigravity headless works | {'✅' if ag_works else '⚠️ untested'} |",
    f"| claude CLI available | {'✅' if results.get('claude_cli_available') else '❌'} |",
    f"| claude -p headless completes | {'✅' if results.get('claude_headless_completes', {}).get('file_written') else '⚠️'} |",
    f"| claude -p 20s survival | {'✅' if results.get('claude_headless_20s_survival', {}).get('survived') else '❌ see #29642'} |",
    f"| .geminiignore exists | {'✅' if results.get('.geminiignore_exists') else '❌ CRITICAL'} |",
    f"| NAZIR_PROJECT_ROOT set | {'✅' if results.get('NAZIR_PROJECT_ROOT_set') else '❌ set this now'} |",
    f"| cgcone available | {'✅' if results.get('cgcone_available') else '⚠️ install'} |",
    f"",
    f"## Recommendation",
    f"",
    f"**Backend:** {results.get('recommendation', 'unknown')}",
    f"",
    f"## Raw JSON",
    f"",
    f"See `{RESULTS_FILE}` for full data.",
]
REPORT_FILE.write_text("\n".join(lines))
ok(f"Markdown report → {REPORT_FILE}")

# Cleanup
shutil.rmtree(PROBE_TMPDIR, ignore_errors=True)

print(f"\n{BOLD}Done. Read memory/probe_report.md before starting Phase 1.{RESET}\n")
