from __future__ import annotations

import json

from fastapi.testclient import TestClient

import api_server


class FakeMessage:
    def __init__(self, content="", message_type="AIMessage", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.__class__ = type(message_type, (), {})


class FakeAgent:
    def invoke(self, inputs, config=None):
        assert config["configurable"]["thread_id"] == "test-thread"
        return {"messages": [FakeMessage("研究结论")]}

    def stream(self, inputs, config=None, stream_mode=None):
        yield {"agent": {"messages": [FakeMessage("流式结论")]}}


def client(monkeypatch):
    monkeypatch.setattr(api_server, "_agent", FakeAgent())
    return TestClient(api_server.app)


def test_health(monkeypatch):
    response = client(monkeypatch).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invoke(monkeypatch):
    response = client(monkeypatch).post(
        "/api/v1/invoke",
        json={"prompt": "分析", "thread_id": "test-thread"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "研究结论"
    assert response.json()["thread_id"] == "test-thread"


def test_stream(monkeypatch):
    with client(monkeypatch).stream(
        "POST", "/api/v1/stream", json={"prompt": "分析", "thread_id": "test-thread"}
    ) as response:
        events = [
            json.loads(line[6:])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    assert [event["type"] for event in events] == ["start", "assistant", "done"]


def test_api_key(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_KEY", "secret")
    test_client = client(monkeypatch)
    assert test_client.post("/api/v1/invoke", json={"prompt": "分析"}).status_code == 401
    response = test_client.post(
        "/api/v1/invoke",
        json={"prompt": "分析", "thread_id": "test-thread"},
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200


def test_invalid_prompt(monkeypatch):
    response = client(monkeypatch).post("/api/v1/invoke", json={"prompt": ""})
    assert response.status_code == 422


def test_openai_chat_completion(monkeypatch):
    response = client(monkeypatch).post(
        "/v1/chat/completions",
        json={
            "model": "research-agent",
            "messages": [{"role": "user", "content": "分析"}],
            "thread_id": "test-thread",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "研究结论"
    assert body["choices"][0]["finish_reason"] == "stop"


def test_openai_stream(monkeypatch):
    with client(monkeypatch).stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "research-agent",
            "messages": [{"role": "user", "content": "分析"}],
            "thread_id": "test-thread",
            "stream": True,
        },
    ) as response:
        lines = list(response.iter_lines())
    assert response.status_code == 200
    assert any('"object": "chat.completion.chunk"' in line for line in lines)
    assert next(line for line in reversed(lines) if line) == "data: [DONE]"
