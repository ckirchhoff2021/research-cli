"""subagents 定义测试（不依赖模型/网络）。"""

from __future__ import annotations

from coding.subagents import build_subagents


def test_subagent_specs_conform_to_deepagents():
    specs = build_subagents()
    names = [s["name"] for s in specs]
    assert names == ["data-analyst", "literature-researcher", "code-implementer"]
    for s in specs:
        assert s["name"] and s["description"] and s["system_prompt"]


def test_subagents_inherit_model_and_tools():
    model, tools = object(), ["t1"]
    specs = build_subagents(model=model, tools=tools)
    assert all(s["model"] is model for s in specs)
    assert all(s["tools"] == ["t1"] for s in specs)
