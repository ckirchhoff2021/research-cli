#!/usr/bin/env bash
# Podcast Studio 启动脚本
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."
PORT="${1:-8901}"
echo "🎙 Podcast Studio → http://127.0.0.1:${PORT}"
exec .venv/bin/python -m uvicorn web.podcast_studio.backend.server:app \
  --host 127.0.0.1 --port "${PORT}"
