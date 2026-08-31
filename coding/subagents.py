"""自定义 SubAgents（遵循 deepagents SubAgent 规范）。

每个 SubAgent 是一个 `deepagents.middleware.subagents.SubAgent` TypedDict：
name / description / system_prompt / tools / model / skills。
主 Agent 通过内置 `task` 工具按名字委派任务。
"""

from __future__ import annotations

from typing import Any

from deepagents.middleware.subagents import SubAgent

DATA_ANALYST_PROMPT = """你是数据分析子代理，负责科研数据的处理与分析：
- 使用 shell/Python 脚本清洗、统计、聚合数据（pandas 可用）
- 产出结论时给出关键数字与依据，必要时生成图表文件到 outputs/ 目录
- 输出格式：先结论，再方法，最后附关键数据
不要编造数据；数据文件不存在时先用文件工具确认路径。"""

LITERATURE_PROMPT = """你是文献调研子代理，负责围绕主题检索与整理文献资料：
- 使用 tavily_search 检索权威来源（论文、官方文档、知名媒体）
- 整理为结构化笔记：主题概述 → 关键发现（附来源 URL）→ 争议/局限
- 引用必须来自检索结果，禁止编造链接
输出语言与用户任务保持一致。"""

CODE_IMPLEMENTER_PROMPT = """你是代码实现子代理，负责把明确的需求实现为可运行代码：
- 先用文件工具阅读相关代码，理解现状再动手修改
- 代码遵循仓库现有风格，完成后运行验证（测试或实际执行）
- 汇报格式：改动文件列表 → 验证结果 → 遗留风险"""


def build_subagents(model: Any = None, tools: list | None = None) -> list[SubAgent]:
    """构建默认 SubAgent 列表。model/tools 缺省时由主 Agent 继承。"""
    common: dict[str, Any] = {}
    if model is not None:
        common["model"] = model
    if tools is not None:
        common["tools"] = tools

    return [
        SubAgent(
            name="data-analyst",
            description="数据处理与实验分析：清洗数据、统计分析、生成图表与结论。"
            "涉及 csv/xlsx/实验数据处理、结果可视化时委派给它。",
            system_prompt=DATA_ANALYST_PROMPT,
            **common,
        ),
        SubAgent(
            name="literature-researcher",
            description="文献与资料调研：围绕主题检索权威来源并整理结构化笔记。"
            "涉及文献综述、背景调研、资料收集时委派给它。",
            system_prompt=LITERATURE_PROMPT,
            **common,
        ),
        SubAgent(
            name="code-implementer",
            description="代码实现与验证：把明确需求实现为可运行代码并自测。"
            "涉及写脚本、修 bug、实现功能时委派给它。",
            system_prompt=CODE_IMPLEMENTER_PROMPT,
            **common,
        ),
    ]
