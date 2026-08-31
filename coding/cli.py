"""命令行入口：本地直接对话调试（无需前端）。

用法：
    uv run python -m coding.cli "帮我分析一下 outputs 目录下有哪些数据文件"
    uv run python -m coding.cli --session <id> "继续上次的话题"
    uv run python -m coding.cli --list          # 列出会话
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .agent_factory import create_agent
from .config import get_settings
from .session_store import SessionStore

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Research Agent CLI")
    parser.add_argument("message", nargs="?", help="任务消息")
    parser.add_argument("--session", default=None, help="会话 id（缺省新建）")
    parser.add_argument("--list", action="store_true", help="列出所有会话")
    args = parser.parse_args()

    settings = get_settings()
    store = SessionStore(settings.sessions_db)

    if args.list:
        for s in store.list_sessions():
            console.print(f"[cyan]{s['session_id']}[/cyan]  {s['title']}  ({s['message_count']} 条, {s['updated_at']})")
        return

    if not args.message:
        parser.print_help()
        sys.exit(1)

    session_id = args.session
    if not session_id:
        session_id = store.create_session()["session_id"]
    elif not store.get_session(session_id):
        store.create_session(session_id)
    console.print(f"[dim]session: {session_id}[/dim]")

    store.add_message(session_id, "user", args.message)
    agent = create_agent(settings)

    with console.status("[bold blue]Agent 执行中..."):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": args.message}]},
            config={"configurable": {"thread_id": session_id}},
        )

    reply = result["messages"][-1].content
    store.add_message(session_id, "assistant", str(reply))
    console.print(Panel(Markdown(str(reply)), title="🤖 Agent", border_style="green"))


if __name__ == "__main__":
    main()
