import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()

# Paths the agent is allowed to write to (subset of PROJECT_ROOT)
ALLOWED_WRITE_DIRS = [PROJECT_ROOT]

# Commands that are never allowed regardless of context
BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf ~", "rm -rf *", "rm -fr /", "rm -fr ~",
    "find / -delete", "find . -delete",
    "mkfs", "dd if=/dev/zero", "dd if=/dev/random",
    "> /dev/sda", "shred /dev",
    "sudo rm", "sudo mkfs", "sudo dd", "sudo chmod -R 777 /",
    ":(){:|:&};:",
    "nc -e", "bash -i >& /dev/tcp",
]

# Max output size returned from shell commands (bytes)
MAX_OUTPUT_BYTES = 50_000

# Test runner command (override via env)
TEST_COMMAND = os.environ.get("NAZIR_TEST_CMD", "python3 -m pytest")
