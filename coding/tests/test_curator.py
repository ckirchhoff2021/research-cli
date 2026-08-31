"""curator 测试：fake 反思 Agent，验证摘要构建与审阅水位推进。"""

from __future__ import annotations

from pathlib import Path

import pytest

import coding.curator as curator_mod
from coding.config import Settings
from coding.curator import Curator, MIN_NEW_MESSAGES


class FakeResult:
    def __init__(self, text):
        self._text = text

    def __getitem__(self, key):
        assert key == "messages"
        return [_FakeText(self._text)]

    def get(self, key, default=None):
        return self[key] if key == "messages" else default


class _FakeText:
    def __init__(self, content):
        self.content = content


class FakeAgent:
    invoked = []

    def invoke(self, inputs, config=None):
        FakeAgent.invoked.append(inputs["messages"][0].content)
        return FakeResult("NO_ACTION")


@pytest.fixture()
def curator(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        sessions_db=tmp_path / "data" / "sessions.db",
        checkpoints_db=tmp_path / "data" / "cp.db",
        static_dir=tmp_path / "static",
        outputs_dir=tmp_path / "outputs",
        skills_dirs=(),
        memory_file=tmp_path / "data" / "memory" / "AGENTS.md",
    )
    settings.ensure_dirs()
    c = Curator(settings)
    c._agent = FakeAgent()
    return c


def test_digest_empty(curator):
    sid = curator.store.create_session()["session_id"]
    digest, max_id = curator.build_digest(sid)
    assert digest == "" and max_id == 0


def test_digest_includes_roles(curator):
    sid = curator.store.create_session()["session_id"]
    curator.store.add_message(sid, "user", "帮我分析实验数据")
    curator.store.add_message(sid, "tool_call", "", meta={"name": "execute", "args": {"cmd": "ls"}})
    curator.store.add_message(sid, "tool_result", "file1.csv\nfile2.csv")
    curator.store.add_message(sid, "assistant", "分析完成")
    digest, max_id = curator.build_digest(sid)
    assert "[user] 帮我分析实验数据" in digest
    assert "execute(" in digest
    assert max_id > 0


def test_run_once_skips_small_and_advances_watermark(curator):
    # 消息太少：跳过反思但推进水位
    sid = curator.store.create_session()["session_id"]
    curator.store.add_message(sid, "user", "hi")
    FakeAgent.invoked.clear()
    curator.run_once()
    assert FakeAgent.invoked == []
    assert curator.store.fetch_new_messages(sid) == []


def test_run_once_reflects_when_enough_messages(curator):
    sid = curator.store.create_session()["session_id"]
    for i in range(MIN_NEW_MESSAGES + 1):
        curator.store.add_message(sid, "user" if i % 2 == 0 else "assistant", f"msg {i}")
    FakeAgent.invoked.clear()
    records = curator.run_once()
    assert len(records) == 1 and records[0]["status"] == "ok"
    assert "msg 0" in FakeAgent.invoked[0]
    assert curator.store.fetch_new_messages(sid) == []
    # 日志落盘
    assert curator.log_path.exists()


def test_run_once_handles_agent_error(curator):
    class BoomAgent:
        def invoke(self, inputs, config=None):
            raise RuntimeError("model down")

    curator._agent = BoomAgent()
    sid = curator.store.create_session()["session_id"]
    for i in range(MIN_NEW_MESSAGES + 1):
        curator.store.add_message(sid, "user", f"msg {i}")
    records = curator.run_once()
    assert records[0]["status"] == "error"
    # 出错也推进水位，避免死循环重放
    assert curator.store.fetch_new_messages(sid) == []
