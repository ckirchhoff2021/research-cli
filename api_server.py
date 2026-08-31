"""Research Agent HTTP API.

Start with:
    uv run python api_server.py --host 0.0.0.0 --port 8322

The API is intentionally separate from the Streamlit UI and the coding
subsystem. It delegates all agent behavior to ``create_research_agent``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from agent import create_research_agent

logger = logging.getLogger("research-cli.api")

app = FastAPI(title="Research CLI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("RESEARCH_API_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent: Any | None = None
_agent_lock = threading.Lock()


class AgentRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="要交给 Research Agent 的任务")
    thread_id: str | None = Field(default=None, description="用于多轮对话的会话 ID")


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str = "research-agent"
    stream: bool = False
    thread_id: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


def _get_agent() -> Any:
    global _agent
    with _agent_lock:
        if _agent is None:
            _agent = create_research_agent()
        return _agent


def _thread_id(value: str | None) -> str:
    if value:
        return value
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"api-{now}-{uuid.uuid4().hex[:8]}"


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return "" if content is None else str(content)


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    """将 OpenAI messages 转换为 Agent 的单轮 prompt。"""
    parts = []
    for message in messages:
        content = _content_text(message.content)
        if content:
            parts.append(f"{message.role}: {content}")
    prompt = "\n\n".join(parts).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="messages content is empty")
    return prompt


def _openai_request_to_agent(request: ChatCompletionRequest) -> AgentRequest:
    return AgentRequest(
        prompt=_messages_to_prompt(request.messages),
        thread_id=request.thread_id,
    )


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def _openai_response(
    request: ChatCompletionRequest,
    result: dict[str, Any],
    completion_id: str,
) -> dict[str, Any]:
    answer = result["answer"]
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "thread_id": result["thread_id"],
    }


def _message_event(message: Any) -> dict[str, Any] | None:
    message_type = type(message).__name__
    if message_type == "AIMessage":
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            return {"type": "tool_call", "calls": tool_calls}
        text = _content_text(getattr(message, "content", ""))
        return {"type": "assistant", "content": text} if text else None
    if message_type == "ToolMessage":
        return {
            "type": "tool_result",
            "tool_call_id": getattr(message, "tool_call_id", None),
            "content": _content_text(getattr(message, "content", "")),
        }
    return None


def _invoke(request: AgentRequest, thread_id: str) -> dict[str, Any]:
    result = _get_agent().invoke(
        {"messages": [HumanMessage(content=request.prompt)]},
        config=_config(thread_id),
    )
    messages = result.get("messages", [])
    events = [event for message in messages if (event := _message_event(message))]
    answer = ""
    if messages:
        answer = _content_text(getattr(messages[-1], "content", messages[-1]))
    return {"thread_id": thread_id, "answer": answer, "events": events}


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _stream_events(request: AgentRequest, thread_id: str, queue: asyncio.Queue,
                   loop: asyncio.AbstractEventLoop) -> None:
    def push(event: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        push({"type": "start", "thread_id": thread_id})
        for update in _get_agent().stream(
            {"messages": [HumanMessage(content=request.prompt)]},
            config=_config(thread_id),
            stream_mode="updates",
        ):
            if not isinstance(update, dict):
                continue
            for node_output in update.values():
                if not isinstance(node_output, dict):
                    continue
                for message in node_output.get("messages", []):
                    event = _message_event(message)
                    if event:
                        push(event)
        push({"type": "done", "thread_id": thread_id})
    except Exception as exc:
        logger.exception("agent stream failed")
        push({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        asyncio.run_coroutine_threadsafe(queue.put(None), loop)


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("RESEARCH_API_KEY")
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid or missing API key")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": app.title, "version": app.version}


@app.get("/v1/models", dependencies=[Depends(require_api_key)])
def list_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "research-agent",
                "object": "model",
                "created": 0,
                "owned_by": "research-cli",
            }
        ],
    }


@app.post("/api/v1/invoke", dependencies=[Depends(require_api_key)])
async def invoke(request: AgentRequest) -> dict[str, Any]:
    thread_id = _thread_id(request.thread_id)
    try:
        return await asyncio.to_thread(_invoke, request, thread_id)
    except Exception as exc:
        logger.exception("agent invoke failed")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/v1/chat/completions", dependencies=[Depends(require_api_key)])
async def chat_completions(request: ChatCompletionRequest) -> Any:
    agent_request = _openai_request_to_agent(request)
    thread_id = _thread_id(agent_request.thread_id)
    completion_id = _completion_id()

    if not request.stream:
        try:
            result = await asyncio.to_thread(_invoke, agent_request, thread_id)
            return _openai_response(request, result, completion_id)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("OpenAI-compatible invoke failed")
            raise HTTPException(
                status_code=500, detail=f"{type(exc).__name__}: {exc}"
            ) from exc

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    threading.Thread(
        target=_stream_events,
        args=(agent_request, thread_id, queue, loop),
        daemon=True,
    ).start()

    async def generate_openai() -> AsyncGenerator[str, None]:
        while True:
            event = await queue.get()
            if event is None:
                yield "data: [DONE]\n\n"
                break
            if event["type"] == "start":
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                }
            elif event["type"] == "assistant":
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": event["content"]},
                            "finish_reason": None,
                        }
                    ],
                }
            elif event["type"] == "done":
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            elif event["type"] == "error":
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"content": event["error"]}, "finish_reason": "stop"}],
                }
            else:
                continue
            yield _sse(chunk)

    return StreamingResponse(
        generate_openai(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/stream", dependencies=[Depends(require_api_key)])
async def stream(request: AgentRequest) -> StreamingResponse:
    thread_id = _thread_id(request.thread_id)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    threading.Thread(
        target=_stream_events,
        args=(request, thread_id, queue, loop),
        daemon=True,
    ).start()

    async def generate() -> AsyncGenerator[str, None]:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Research CLI API server")
    parser.add_argument("--host", default=os.getenv("RESEARCH_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("RESEARCH_API_PORT", "8322")))
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
