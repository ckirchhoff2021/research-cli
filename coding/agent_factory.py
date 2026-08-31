"""Agent 工厂：组装 deepagents Agent（模型 + 工具 + 技能 + SubAgents + 持久化）。"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

from .config import Settings, brain_model, get_settings
from .subagents import build_subagents

_CHECKPOINTER_LOCK = threading.Lock()
_CHECKPOINTER: SqliteSaver | None = None

# 默认系统提示：定位 + 输出规范
SYSTEM_PROMPT = """你是一个科研助理 Agent，服务于日常科研任务：数据处理、实验分析、文献整理、代码实现、结果可视化。

工作准则：
1. 严谨客观，不编造数据与引用；不确定时明确标注。
2. 复杂任务先拆解为步骤，可委派给子代理（data-analyst / literature-researcher / code-implementer）。
3. 产出的图片、视频、音频、HTML 等文件统一写入 outputs/ 目录，并在回复中给出相对路径（如 outputs/xxx.png），前端会自动预览。
4. 数据分析结果优先用 Markdown 表格呈现。
5. 回复语言与用户保持一致。"""


def build_chat_model(cfg=None, **overrides) -> BaseChatModel:
    """按配置构建 OpenAI 协议兼容的聊天模型。"""
    cfg = cfg or brain_model()
    if not cfg.available:
        raise RuntimeError(
            "主模型未配置：请在 .env 中设置 BRAIN_API_KEY / BRAIN_API_URL / BRAIN_MODEL_NAME"
        )
    return ChatOpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=overrides.pop("temperature", 0.7),
        timeout=overrides.pop("timeout", 300),
        streaming=True,
        **overrides,
    )


def get_checkpointer(db_path: str | Path) -> SqliteSaver:
    """进程级共享的 SQLite checkpointer（按 db 路径缓存）。"""
    global _CHECKPOINTER
    with _CHECKPOINTER_LOCK:
        if _CHECKPOINTER is None:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            _CHECKPOINTER = SqliteSaver(conn)
        return _CHECKPOINTER


def _custom_tools() -> list:
    """复用仓库 tools/ 下的自定义工具（web 搜索等）。"""
    import sys

    repo_root = get_settings().repo_root
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from tools.custom_tools import get_custom_tools

        return get_custom_tools()
    except Exception:
        return []


def create_agent(settings: Settings | None = None, model: BaseChatModel | None = None):
    """创建带持久化 checkpointer 的科研 Agent（compiled graph）。"""
    settings = settings or get_settings()
    chat_model = model or build_chat_model()
    tools = _custom_tools()

    return create_deep_agent(
        model=chat_model,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        subagents=build_subagents(model=chat_model, tools=tools or None),
        skills=list(settings.skills_dirs),
        memory=[str(settings.memory_file)],
        backend=LocalShellBackend(
            root_dir=str(settings.repo_root),
            virtual_mode=False,
            inherit_env=True,
        ),
        checkpointer=get_checkpointer(settings.checkpoints_db),
        name="research-agent",
    )
