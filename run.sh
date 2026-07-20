#!/bin/bash
# Usage: ./run.sh <prompt-file>
# Example: ./run.sh task.txt

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <prompt-file>"
    echo "  Reads the task prompt from the given file and runs main.py with -s -c"
    exit 1
fi

PROMPT_FILE="$1"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: file not found: $PROMPT_FILE"
    exit 1
fi

TASK_PROMPT=$(cat "$PROMPT_FILE")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python main.py --task_prompt "$TASK_PROMPT" -s -c
