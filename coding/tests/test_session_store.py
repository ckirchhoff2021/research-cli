"""session_store 单元测试。"""

from __future__ import annotations

from pathlib import Path

from coding.session_store import SessionStore


def make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.db")


def test_create_and_get_session(tmp_path):
    store = make_store(tmp_path)
    s = store.create_session(title="测试会话")
    assert s["session_id"]
    assert s["title"] == "测试会话"
    assert store.get_session(s["session_id"])["title"] == "测试会话"


def test_list_sessions_ordered_by_update(tmp_path):
    store = make_store(tmp_path)
    s1 = store.create_session(title="A")
    s2 = store.create_session(title="B")
    store.add_message(s2["session_id"], "user", "hi")
    ids = [s["session_id"] for s in store.list_sessions()]
    assert ids[0] == s2["session_id"]
    assert s1["session_id"] in ids


def test_add_and_list_messages(tmp_path):
    store = make_store(tmp_path)
    sid = store.create_session()["session_id"]
    store.add_message(sid, "user", "问题")
    store.add_message(sid, "tool_call", "", meta={"name": "tavily_search", "args": {"q": 1}})
    store.add_message(sid, "tool_result", "结果")
    store.add_message(sid, "assistant", "回答")
    msgs = store.list_messages(sid)
    assert [m["role"] for m in msgs] == ["user", "tool_call", "tool_result", "assistant"]
    assert msgs[1]["meta"]["name"] == "tavily_search"
    assert store.get_session(sid)["message_count"] == 4


def test_auto_title_update_and_delete(tmp_path):
    store = make_store(tmp_path)
    sid = store.create_session()["session_id"]
    store.update_title(sid, "新标题")
    assert store.get_session(sid)["title"] == "新标题"
    store.delete_session(sid)
    assert store.get_session(sid) is None
    assert store.list_messages(sid) == []


def test_curator_watermark(tmp_path):
    store = make_store(tmp_path)
    sid = store.create_session()["session_id"]
    store.add_message(sid, "user", "m1")
    store.add_message(sid, "assistant", "m2")
    new = store.fetch_new_messages(sid)
    assert len(new) == 2
    store.mark_reviewed(sid, new[-1]["id"])
    assert store.fetch_new_messages(sid) == []
    store.add_message(sid, "user", "m3")
    new2 = store.fetch_new_messages(sid)
    assert len(new2) == 1 and new2[0]["content"] == "m3"


def test_add_message_creates_missing_session(tmp_path):
    store = make_store(tmp_path)
    store.add_message("ghost-session", "user", "hi")
    assert store.get_session("ghost-session") is not None
