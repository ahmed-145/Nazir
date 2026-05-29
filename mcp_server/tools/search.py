import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

import subprocess
import shutil
from pathlib import Path
from security.validate_path import validate_path
from mcp_server.config import PROJECT_ROOT, MAX_OUTPUT_BYTES


def search_in_files(pattern: str, path: str = ".", file_glob: str = None) -> str:
    """
    Search for a pattern using ripgrep (rg). Falls back to grep if rg unavailable.
    Returns matching lines with file:line context.
    """
    search_root = validate_path(path)

    if shutil.which("rg"):
        cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
        if file_glob:
            cmd += ["--glob", file_glob]
        cmd += [pattern, str(search_root)]
    else:
        cmd = ["grep", "-rn", "--include", file_glob or "*", pattern, str(search_root)]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=20,
    )
    output = result.stdout
    if not output.strip():
        return f"No matches for '{pattern}' in {search_root}"
    if len(output) > MAX_OUTPUT_BYTES:
        output = output[:MAX_OUTPUT_BYTES] + "\n[truncated]"
    return output


def find_files(pattern: str, path: str = ".") -> str:
    """
    Find files by name pattern using rg --files or find.
    """
    search_root = validate_path(path)

    if shutil.which("rg"):
        result = subprocess.run(
            ["rg", "--files", "--glob", pattern, str(search_root)],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT), timeout=20,
        )
    else:
        result = subprocess.run(
            ["find", str(search_root), "-name", pattern, "-type", "f"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT), timeout=20,
        )

    output = result.stdout.strip()
    # Make paths relative to PROJECT_ROOT for readability
    lines = []
    for line in output.splitlines():
        try:
            lines.append(str(Path(line).relative_to(PROJECT_ROOT)))
        except ValueError:
            lines.append(line)
    return "\n".join(lines) if lines else f"No files matching '{pattern}' in {search_root}"
