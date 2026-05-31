#!/usr/bin/env bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$')
    set +a
fi

export NAZIR_PROJECT_ROOT="$PROJECT_ROOT"
cd "$PROJECT_ROOT"
mkdir -p logs

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [run-claude] $*" | tee -a logs/agent.log; }

log "Task-loop wrapper started."

# Restore Gemini session UUIDs from disk (no API call — just load saved sessions)
python3 -c "
import sys, os; sys.path.insert(0,'$PROJECT_ROOT'); os.environ['NAZIR_PROJECT_ROOT']='$PROJECT_ROOT'
from orchestrator.gemini_runner import load_sessions
from pathlib import Path
load_sessions(Path('memory/gemini_sessions.json'))
" 2>&1 | tee -a logs/agent.log || log "Session restore failed (non-fatal)"

TASK_FILE="$PROJECT_ROOT/memory/current_task.md"

while true; do
    [ ! -f "$TASK_FILE" ] && { sleep 5; continue; }
    TASK=$(cat "$TASK_FILE" 2>/dev/null || echo "")

    case "$TASK" in
        "PAUSE") log "Paused."; sleep 30; continue ;;
        "DONE"|"") sleep 5; continue ;;
    esac

    log "Starting task: ${TASK:0:80}..."
    touch /tmp/nazir-heartbeat

    claude --dangerously-skip-permissions -p "$TASK" < /dev/null 2>&1 | tee -a logs/agent.log
    EXIT_CODE=${PIPESTATUS[0]}
    log "Claude exited $EXIT_CODE."

    CURRENT=$(cat "$TASK_FILE" 2>/dev/null || echo "")
    [ "$CURRENT" = "$TASK" ] && echo "DONE" > "$TASK_FILE"
    sleep 5
done
