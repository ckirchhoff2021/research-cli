#!/usr/bin/env bash
# Drama Studio 启动脚本（使用项目自带 venv）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."
PORT="${1:-8899}"
echo "🎬 Drama Studio → http://127.0.0.1:${PORT}"
exec .venv/bin/python -m uvicorn web.drama_studio.backend.server:app \
  --host 127.0.0.1 --port "${PORT}"

