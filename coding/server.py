"""FastAPI 服务端：SSE 流式对话 + 会话管理 + outputs 文件预览。

启动：
    uv run python -m coding.server [--port 8321] [--no-curator]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from .agent_factory import create_agent
from .config import get_settings
from .curator import Curator
from .session_store import SessionStore

logger = logging.getLogger("coding.server")

settings = get_settings()
store = SessionStore(settings.sessions_db)

_agent = None
_agent_lock = threading.Lock()


def get_agent():
    """懒加载并缓存 Agent（compiled graph）。"""
    global _agent
    with _agent_lock:
        if _agent is None:
            _agent = create_agent(settings)
        return _agent


app = FastAPI(title="Research Agent", version="0.1.0")

MEDIA_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    ".mp4", ".webm", ".mov",
    ".mp3", ".wav", ".m4a", ".flac", ".ogg",
    ".html", ".pdf", ".csv", ".json", ".md", ".txt",
}


# ---------- schemas ----------

class ChatRequest(BaseModel):
    message: str


class SessionCreate(BaseModel):
    title: str | None = None


class TitleUpdate(BaseModel):
    title: str


# ---------- 事件流 ----------

def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content) if content is not None else ""


def _run_agent_turn(session_id: str, user_message: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """在工作线程里跑一轮 Agent，把事件推给 SSE 队列。"""

    def push(event: dict[str, Any]):
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        agent = get_agent()
        store.add_message(session_id, "user", user_message)
        push({"type": "user", "content": user_message})

        final_text = ""
        plan_seen = False  # 首次 write_todos 作为规划卡片
        plan_msg_id = None  # 持久化的 plan 消息 id，用于更新 meta
        seen_tool_calls: set[str] = set()  # 去重：同一 tool_call_id 不重复推
        current_todos: list[dict] = []  # 追踪当前 todos 状态，用于推送更新
        config = {"configurable": {"thread_id": session_id}}

        for event in agent.stream(
            {"messages": [HumanMessage(content=user_message)]},
            config=config,
            stream_mode="updates",
        ):
            for _node, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue

                # TodoListMiddleware 在 tools 节点输出 todos 列表，用于状态更新
                if "todos" in node_output and isinstance(node_output["todos"], list):
                    new_todos = node_output["todos"]
                    if plan_seen and new_todos != current_todos:
                        current_todos = new_todos
                        shrunk = _shrink_args({"todos": new_todos})["todos"]
                        push({"type": "plan_update", "todos": shrunk})
                        # 同步更新数据库里 plan 消息的 meta
                        if plan_msg_id is not None:
                            try:
                                store.update_message_meta(
                                    session_id, plan_msg_id, {"todos": shrunk}
                                )
                            except Exception:
                                pass

                for msg in node_output.get("messages", []):
                    msg_type = type(msg).__name__

                    if msg_type == "AIMessage":
                        text = _content_to_text(msg.content)
                        tool_calls = getattr(msg, "tool_calls", None) or []

                        # 推送助手文本（最终回复）
                        if text.strip():
                            # 取最长的作为最终文本（避免中间短消息覆盖）
                            if len(text) > len(final_text):
                                final_text = text
                                store.add_message(session_id, "assistant", text)
                            push({"type": "assistant", "content": text})

                        for tc in tool_calls:
                            tc_id = tc.get("id") or f"{tc.get('name')}-{len(seen_tool_calls)}"
                            if tc_id in seen_tool_calls:
                                continue
                            seen_tool_calls.add(tc_id)
                            name = tc.get("name", "unknown")
                            args = tc.get("args", {}) or {}
                            shrunk = _shrink_args(args)

                            if name == "write_todos" and isinstance(args.get("todos"), list):
                                if not plan_seen:
                                    # 首次 write_todos → 规划卡片
                                    plan_seen = True
                                    current_todos = args["todos"]
                                    shrunk_todos = shrunk["todos"]
                                    push({"type": "plan", "todos": shrunk_todos})
                                    plan_msg_id = store.add_message(
                                        session_id, "plan", "",
                                        meta={"todos": shrunk_todos},
                                    )
                                else:
                                    # 后续 write_todos 是状态更新，已由 plan_update 处理
                                    pass
                            else:
                                # 普通工具调用 → 时间线步骤
                                store.add_message(
                                    session_id, "tool_call", "",
                                    meta={"name": name, "args": shrunk, "tc_id": tc_id},
                                )
                                push({"type": "tool_call", "id": tc_id, "name": name, "args": shrunk})

                    elif msg_type == "ToolMessage":
                        tc_id = getattr(msg, "tool_call_id", None)
                        result = _content_to_text(msg.content)
                        truncated = result[:4000]
                        # write_todos 的 ToolMessage 只是 "Updated todo list..."，已由 plan_update 处理
                        is_todo_ack = "Updated todo list" in truncated[:50]
                        if not is_todo_ack:
                            store.add_message(session_id, "tool_result", truncated,
                                              meta={"tc_id": tc_id} if tc_id else None)
                            push({"type": "tool_result", "id": tc_id, "content": truncated})

        push({"type": "done", "content": final_text})
    except Exception as e:
        logger.exception("agent turn failed")
        push({"type": "error", "content": f"{type(e).__name__}: {e}"})
    finally:
        asyncio.run_coroutine_threadsafe(queue.put(None), loop)


def _shrink_args(args: dict, max_len: int = 1200) -> dict:
    """压缩工具参数用于展示：保留 dict/list 原始结构（前端按类型渲染），仅截断超长字符串。"""
    shrunk = {}
    for k, v in args.items():
        if isinstance(v, str):
            shrunk[k] = v[:max_len] + ("..." if len(v) > max_len else "")
        elif isinstance(v, (dict, list)):
            shrunk[k] = v  # 保留结构，如 write_todos 的 todos 数组
        else:
            shrunk[k] = v
    return shrunk


# ---------- API ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/api/sessions")
def list_sessions():
    return store.list_sessions()


@app.post("/api/sessions")
def create_session(body: SessionCreate):
    return store.create_session(title=body.title)


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    store.delete_session(session_id)
    return {"status": "deleted"}


@app.patch("/api/sessions/{session_id}/title")
def update_title(session_id: str, body: TitleUpdate):
    store.update_title(session_id, body.title.strip() or "新会话")
    return store.get_session(session_id)


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    if not store.get_session(session_id):
        raise HTTPException(404, "session not found")
    return store.list_messages(session_id)


@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatRequest):
    if not store.get_session(session_id):
        raise HTTPException(404, "session not found")
    if not body.message.strip():
        raise HTTPException(400, "empty message")

    # 首条用户消息自动生成标题
    session = store.get_session(session_id)
    if session and session["message_count"] == 0 and (session["title"] in ("新会话", "")):
        title = re.sub(r"\s+", " ", body.message.strip())[:40]
        store.update_title(session_id, title or "新会话")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    threading.Thread(
        target=_run_agent_turn,
        args=(session_id, body.message.strip(), queue, loop),
        daemon=True,
    ).start()

    async def gen() -> AsyncGenerator[str, None]:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.get("/files/{file_path:path}")
def preview_file(file_path: str):
    """预览 outputs/ 下的产出文件（图片/视频/音频/HTML 等）。"""
    base = settings.outputs_dir.resolve()
    target = (base / file_path).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target)


app.mount("/", StaticFiles(directory=str(settings.static_dir), html=True), name="static")


def main():
    parser = argparse.ArgumentParser(description="Research Agent 服务")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--no-curator", action="store_true", help="禁用后台自进化 curator")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if not args.no_curator:
        Curator(settings).start_background()
        logger.info("curator background thread started")

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
