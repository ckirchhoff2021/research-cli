#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ $# -eq 0 ]; then
    echo "Usage:"
    echo "  ./run.sh <prompt-file>    Run CLI with task from file"
    echo "  ./run.sh --web            Start Streamlit web interface"
    exit 1
fi

if [ "$1" == "--web" ]; then
    uv run streamlit run app.py
    exit 0
fi

PROMPT_FILE="$1"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: file not found: $PROMPT_FILE"
    exit 1
fi

TASK_PROMPT=$(cat "$PROMPT_FILE")

python main.py --task_prompt "$TASK_PROMPT" -s -c
