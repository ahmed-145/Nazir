Phase 1: Hardened DesktopCommanderMCP.

Phase 0.5 is complete. Backend decision: Gemini CLI.
Two installs needed first (ask user):
  sudo apt install ripgrep
  npm install -g cgcone

Then Phase 1:
1. Write AppArmor named profile for desktop-commander
2. Install DesktopCommanderMCP via claude mcp add
3. Sync to Gemini CLI via cgcone
4. Test: read file, run echo, attempt write outside PROJECT_ROOT
