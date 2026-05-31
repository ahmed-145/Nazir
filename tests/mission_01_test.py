#!/usr/bin/env python3
"""
Mission 01 acceptance test — Phase 9.

Tests the dry_run parameter added to safe_run_command.
Run by TesterAgent during the pipeline; also referenced in test_all_phases.py Phase 9.

Exit 0 = all pass. Exit 1 = failures.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

G, R, RE = "\033[92m", "\033[91m", "\033[0m"
results = []

def ok(name, detail=""):
    results.append(True)
    print(f"  {G}PASS{RE}  {name}" + (f"  →  {detail}" if detail else ""))

def fail(name, detail=""):
    results.append(False)
    print(f"  {R}FAIL{RE}  {name}" + (f"\n         {detail}" if detail else ""))


print("\nmission-01 acceptance tests — dry_run flag in safe_run_command\n")

# ── Import ────────────────────────────────────────────────────────────────────
try:
    from mcp_server.tools.shell import safe_run_command
    ok("safe_run_command importable")
except ImportError as e:
    fail("import failed", str(e))
    sys.exit(1)

# ── Signature accepts dry_run ─────────────────────────────────────────────────
try:
    import inspect
    sig = inspect.signature(safe_run_command)
    assert "dry_run" in sig.parameters, \
        f"dry_run not in signature: {list(sig.parameters)}"
    ok("safe_run_command signature has dry_run parameter",
       str(list(sig.parameters)))
except AssertionError as e:
    fail("dry_run parameter missing from signature", str(e))
except Exception as e:
    fail("signature check failed", str(e))

# ── dry_run=True: returns DRY_RUN prefix, does NOT execute ───────────────────
try:
    import os as _os
    _sentinel = "/tmp/nazir_dryrun_sentinel"
    if _os.path.exists(_sentinel):
        _os.unlink(_sentinel)

    out = safe_run_command(f"touch {_sentinel}", dry_run=True)
    assert "DRY_RUN" in out, f"missing DRY_RUN prefix: {repr(out)}"
    assert not _os.path.exists(_sentinel), \
        "command was actually executed — sentinel file was created!"
    assert f"touch {_sentinel}" in out, \
        f"command text missing from dry_run output: {repr(out)}"
    ok("dry_run=True: returns DRY_RUN prefix, does not execute command",
       repr(out[:60]))
except AssertionError as e:
    fail("dry_run=True behavior wrong", str(e))
except TypeError as e:
    fail("dry_run parameter not accepted", str(e))
except Exception as e:
    fail("dry_run=True test failed", str(e))

# ── dry_run=False (default): executes normally ────────────────────────────────
try:
    out2 = safe_run_command("echo EXECUTE_OK", dry_run=False)
    assert "EXECUTE_OK" in out2, f"command not executed: {repr(out2)}"
    ok("dry_run=False: command executes normally", repr(out2.strip()))
except Exception as e:
    fail("dry_run=False (explicit) failed", str(e))

# ── Default (no dry_run arg): still works ─────────────────────────────────────
try:
    out3 = safe_run_command("echo DEFAULT_OK")
    assert "DEFAULT_OK" in out3, f"default broke: {repr(out3)}"
    ok("default (no dry_run arg): backward compatible, command executes",
       repr(out3.strip()))
except Exception as e:
    fail("default behavior broken", str(e))

# ── Blocklist still enforced in dry_run mode ──────────────────────────────────
try:
    try:
        safe_run_command("rm -rf /", dry_run=True)
        fail("blocklist not enforced in dry_run mode — CRITICAL")
    except PermissionError:
        ok("blocklist enforced even with dry_run=True (rm -rf blocked)")
except Exception as e:
    fail("blocklist dry_run enforcement check failed", str(e))

# ── dry_run default is False ──────────────────────────────────────────────────
try:
    sig2 = inspect.signature(safe_run_command)
    default = sig2.parameters["dry_run"].default
    assert default is False, f"expected default=False, got {repr(default)}"
    ok("dry_run default value is False")
except AssertionError as e:
    fail("dry_run default wrong", str(e))
except Exception as e:
    fail("default check failed", str(e))

# ── Summary ───────────────────────────────────────────────────────────────────
n_pass = sum(results)
n_fail = len(results) - n_pass
print(f"\n  {n_pass} passed  {n_fail} failed  {len(results)} total\n")
sys.exit(0 if n_fail == 0 else 1)
