import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()


def validate_path(requested: str) -> Path:
    """
    Resolve path and reject anything outside PROJECT_ROOT.
    Handles symlinks, .., and encoded traversal attempts.
    """
    try:
        resolved = Path(requested).resolve()
    except (OSError, ValueError) as e:
        raise PermissionError(f"Invalid path: {requested}") from e

    if not str(resolved).startswith(str(PROJECT_ROOT)):
        raise PermissionError(
            f"Path outside PROJECT_ROOT.\n"
            f"  Requested: {requested}\n"
            f"  Resolved:  {resolved}\n"
            f"  Root:      {PROJECT_ROOT}"
        )
    return resolved
