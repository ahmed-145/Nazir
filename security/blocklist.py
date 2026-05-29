"""
Command blocklist for safe_run_command.
Blocks patterns that should never run from an agent regardless of context.
"""

BLOCKED_PATTERNS = [
    # Recursive deletes
    "rm -rf /", "rm -rf ~", "rm -rf *", "rm -fr /", "rm -fr ~",
    "find / -delete", "find . -delete",
    # Disk destruction
    "mkfs", "dd if=/dev/zero", "dd if=/dev/random",
    "> /dev/sda", "shred /dev",
    # Privilege escalation
    "sudo ",  # block ALL sudo — agent never needs root
    "chmod -R 777 /",
    # Fork bomb
    ":(){:|:&};:",
    # Key exfiltration
    "cat .env", "cat ~/.ssh", "cat .git/config",
    # Network exfiltration (use Gemini's policy TOML for curl/wget blocking)
    "nc -e", "bash -i >& /dev/tcp",
]


def check_command(cmd: str) -> None:
    """
    Raise PermissionError if cmd matches any blocked pattern.
    Called before every shell execution in the MCP server.
    """
    cmd_lower = cmd.lower().strip()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            raise PermissionError(f"Blocked command pattern: '{pattern}'")
