import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

import subprocess
from mcp_server.config import PROJECT_ROOT


def _git(args: list[str], timeout: int = 15) -> str:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=timeout,
    )
    return (result.stdout + result.stderr).strip()


def git_status() -> str:
    return _git(["status", "--short", "--branch"])


def git_diff(staged: bool = False) -> str:
    args = ["diff", "--stat", "--patch"]
    if staged:
        args.append("--staged")
    output = _git(args)
    if len(output) > 20_000:
        output = output[:20_000] + "\n[diff truncated]"
    return output or "(no changes)"


def git_log(n: int = 10) -> str:
    return _git(["log", f"-{n}", "--oneline", "--decorate"])


def git_commit(message: str) -> str:
    if not message.strip():
        raise ValueError("Commit message cannot be empty")
    # Stage all tracked modifications (not untracked — explicit add required)
    _git(["add", "-u"])
    result = _git(["commit", "-m", message])
    return result


def git_add(paths: list[str]) -> str:
    if not paths:
        raise ValueError("Provide at least one path to stage")
    return _git(["add", "--"] + paths)


def git_stash(message: str = "") -> str:
    args = ["stash"]
    if message:
        args += ["push", "-m", message]
    return _git(args)


def git_stash_pop() -> str:
    return _git(["stash", "pop"])
