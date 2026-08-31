"""server API 测试：用 fake agent 替换真实模型调用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

import coding.server as server


class _FakeMsg:
    def __init__(self, content="", tool_calls=None, cls="AIMessage"):
        self.content = content
        self.tool_calls = tool_calls or []
        self.__class__ = type(cls, (), {})  # 让 type(msg).__name__ 生效


def _fake_ai(content):
    m = _FakeMsg(content)
    return m


class FakeAgent:
    """模拟 deepagents compiled graph 的 stream(updates) 行为。"""

    def stream(self, inputs, config=None, stream_mode=None):
        yield {"agent": {"messages": [_fake_ai("## 结论\n\n| 指标 | 值 |\n|---|---|\n| A | 1 |\n\n输出文件: outputs/demo.png")]}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "get_agent", lambda: FakeAgent())
    monkeypatch.setattr(server.store, "db_path", tmp_path / "s.db")
    server.store.__init__(tmp_path / "s.db")
    return TestClient(server.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_session_crud(client):
    s = client.post("/api/sessions", json={"title": None}).json()
    sid = s["session_id"]
    assert client.get("/api/sessions").json()[0]["session_id"] == sid
    client.patch(f"/api/sessions/{sid}/title", json={"title": "改名"})
    assert client.get("/api/sessions").json()[0]["title"] == "改名"
    client.delete(f"/api/sessions/{sid}")
    assert client.get("/api/sessions").json() == []


def test_chat_sse_flow(client):
    sid = client.post("/api/sessions", json={}).json()["session_id"]
    with client.stream("POST", f"/api/sessions/{sid}/chat", json={"message": "分析数据"}) as resp:
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    types = [e["type"] for e in events]
    assert "user" in types and "assistant" in types and types[-1] == "done"
    # 自动标题
    assert client.get("/api/sessions").json()[0]["title"] == "分析数据"
    # 消息已持久化
    msgs = client.get(f"/api/sessions/{sid}/messages").json()
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles


def test_chat_404_unknown_session(client):
    r = client.post("/api/sessions/nope/chat", json={"message": "hi"})
    assert r.status_code == 404


def test_file_preview_sandbox(client, tmp_path, monkeypatch):
    out = server.settings.outputs_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "demo.png").write_bytes(b"\x89PNG fake")
    r = client.get("/files/demo.png")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    # 路径穿越被拦截
    assert client.get("/files/../.env").status_code == 404


def test_index_html_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Research Agent" in r.text
