import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent))

from pathlib import Path
from security.validate_path import validate_path
from mcp_server.config import PROJECT_ROOT, MAX_OUTPUT_BYTES


def safe_read_file(path: str) -> str:
    resolved = validate_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Not a file: {resolved}")
    content = resolved.read_text(errors="replace")
    if len(content) > MAX_OUTPUT_BYTES:
        content = content[:MAX_OUTPUT_BYTES] + f"\n[truncated — file is {resolved.stat().st_size} bytes]"
    return content


def safe_write_file(path: str, content: str) -> str:
    resolved = validate_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content)
    return f"Written: {resolved} ({len(content)} bytes)"


def list_dir(path: str = ".") -> str:
    resolved = validate_path(path)
    if not resolved.is_dir():
        raise ValueError(f"Not a directory: {resolved}")
    entries = sorted(resolved.iterdir(), key=lambda p: (p.is_file(), p.name))
    lines = []
    for e in entries:
        if e.name.startswith("."):
            continue
        marker = "/" if e.is_dir() else ""
        size = f"  {e.stat().st_size:>8} B" if e.is_file() else ""
        lines.append(f"{e.name}{marker}{size}")
    return "\n".join(lines) or "(empty)"
