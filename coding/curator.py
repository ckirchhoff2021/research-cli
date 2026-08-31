"""Curator：后台自进化子代理（参考 Hermes 的自动 curation 机制）。

职责：
1. 周期性扫描所有会话中 curator 尚未审阅的消息；
2. 有足够新内容时，把会话摘要交给"反思 Agent"（optimizer 模型驱动）；
3. 反思 Agent 用文件工具完成两类沉淀：
   - 把稳定的用户偏好 / 环境事实 / 纠正式经验追加到 memory/AGENTS.md；
   - 把重复出现的多步工作流沉淀为新技能（data/skills/<name>/SKILL.md）。
4. 审阅水位写回 sessions.last_curator_msg_id，日志落 data/curator.log.jsonl。

独立调试：
    uv run python -m coding.curator --once     # 前台跑一轮
    uv run python -m coding.curator --daemon   # 前台常驻
服务端会在启动时以守护线程方式拉起。
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from datetime import datetime
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_core.messages import HumanMessage

from .agent_factory import build_chat_model
from .config import Settings, get_settings, optimizer_model
from .session_store import SessionStore

logger = logging.getLogger("coding.curator")

MIN_NEW_MESSAGES = 4          # 至少积累 N 条新消息才值得反思
MAX_DIGEST_CHARS = 12000      # 摘要长度上限，防止上下文爆炸

CURATOR_PROMPT = """你是 Curator（策展人）子代理，负责从用户的科研会话中提炼可复用的长期知识，完成 Agent 的自进化。

你能读到的背景：
- memory/AGENTS.md：Agent 的长期记忆（已注入你的系统提示，也可用 read_file 重读）。
- skills/：你沉淀的技能目录（每个技能一个子目录，内含 SKILL.md）。

当前会话的新增内容如下（user=用户，assistant=Agent，tool_call/tool_result=工具交互摘要）：

{digest}

请依次判断并行动（只做有明确价值的沉淀，宁缺毋滥）：

1. 长期记忆：会话中是否出现【稳定的用户偏好、环境事实、对 Agent 的纠正】？
   若有，用 write_file 把新条目追加进 memory/AGENTS.md 的对应小节
   （## 用户偏好 / ## 环境与约定 / ## 经验教训，不存在则创建）。
   只写陈述性事实，不写一次性任务细节（如某次输出路径、临时结论）。

2. 技能沉淀：会话中是否出现【可复用的多步工作流】（≥3 步、有明确输入输出、未来大概率重复）？
   若有且 skills/ 下尚无对应技能，创建 skills/<小写连字符名>/SKILL.md，
   开头必须是 YAML frontmatter：
   ---
   name: <小写连字符名>
   description: <一句话说明何时触发该技能>
   ---
   正文写清：适用场景、步骤、关键命令、注意事项。

3. 若两类都不满足，直接回复 NO_ACTION，不要修改任何文件。

完成后用一句话总结你做了什么（或 NO_ACTION）。"""


class Curator:
    """会话监视 + 自进化执行器。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.store = SessionStore(self.settings.sessions_db)
        self.log_path = self.settings.data_dir / "curator.log.jsonl"
        self._agent = None
        self._stop = threading.Event()

    # ---------- 摘要 ----------

    def build_digest(self, session_id: str) -> tuple[str, int]:
        """把未审阅消息压成文本摘要；返回 (digest, 最大消息id)。"""
        new_msgs = self.store.fetch_new_messages(session_id)
        if not new_msgs:
            return "", 0
        lines: list[str] = []
        for m in new_msgs:
            role = m["role"]
            content = (m.get("content") or "").strip()
            meta = m.get("meta") or {}
            if role == "tool_call":
                content = f"{meta.get('name', 'tool')}({json.dumps(meta.get('args', {}), ensure_ascii=False)[:200]})"
            elif role == "tool_result":
                content = content[:300]
            else:
                content = content[:1500]
            if content:
                lines.append(f"[{role}] {content}")
        digest = "\n\n".join(lines)
        if len(digest) > MAX_DIGEST_CHARS:
            digest = digest[:MAX_DIGEST_CHARS] + "\n...(已截断)"
        return digest, int(new_msgs[-1]["id"])

    # ---------- 反思 Agent ----------

    def _get_agent(self):
        if self._agent is None:
            cfg = optimizer_model()
            if not cfg.available:
                raise RuntimeError("curator 模型未配置（OPTIMIZER_* / BRAIN_* 均缺失）")
            data_dir = self.settings.data_dir
            self._agent = create_deep_agent(
                model=build_chat_model(cfg, temperature=0.2),
                system_prompt=(
                    "你是科研 Agent 框架的 Curator。只允许修改 memory/ 与 skills/ 下的文件。"
                ),
                backend=LocalShellBackend(
                    root_dir=str(data_dir),
                    virtual_mode=False,
                    inherit_env=True,
                ),
                memory=[str(data_dir / "memory" / "AGENTS.md")],
                name="curator",
            )
        return self._agent

    def _log(self, record: dict[str, Any]) -> None:
        record["timestamp"] = datetime.now().isoformat(timespec="seconds")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("curator: %s", record)

    # ---------- 单轮 ----------

    def run_once(self) -> list[dict]:
        """扫描所有会话并反思；返回本轮处理记录。"""
        records: list[dict] = []
        for session in self.store.list_sessions():
            session_id = session["session_id"]
            try:
                digest, max_id = self.build_digest(session_id)
            except Exception as e:  # 存储异常不应阻断其他会话
                self._log({"session_id": session_id, "status": "error", "error": str(e)})
                continue
            if not digest or len(digest.splitlines()) < MIN_NEW_MESSAGES:
                if max_id:  # 内容太少不值得反思，但也推进水位避免重复累积
                    self.store.mark_reviewed(session_id, max_id)
                continue

            prompt = CURATOR_PROMPT.format(digest=digest)
            try:
                agent = self._get_agent()
                result = agent.invoke(
                    {"messages": [HumanMessage(content=prompt)]},
                    config={
                        "configurable": {
                            "thread_id": f"curator-{session_id}-{int(time.time())}"
                        }
                    },
                )
                final = result["messages"][-1].content if result.get("messages") else ""
                status = "ok"
            except Exception as e:
                final, status = f"{type(e).__name__}: {e}", "error"

            self.store.mark_reviewed(session_id, max_id)
            record = {
                "session_id": session_id,
                "status": status,
                "reviewed_up_to": max_id,
                "summary": str(final)[:500],
            }
            self._log(record)
            records.append(record)
        return records

    # ---------- 守护线程 ----------

    def run_daemon(self, once: bool = False) -> None:
        """阻塞循环；once=True 时只跑一轮（调试用）。"""
        logger.info("curator daemon started (interval=%.0fs)", self.settings.curator_interval)
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as e:
                self._log({"status": "loop_error", "error": str(e)})
            if once:
                break
            self._stop.wait(self.settings.curator_interval)

    def start_background(self) -> threading.Thread:
        t = threading.Thread(target=self.run_daemon, name="curator", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()


def main() -> None:
    parser = argparse.ArgumentParser(description="Curator 自进化子代理")
    parser.add_argument("--once", action="store_true", help="只扫描一轮后退出")
    parser.add_argument("--interval", type=float, default=None, help="循环间隔秒数")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    if args.interval:
        settings = Settings(
            **{**settings.__dict__, "curator_interval": args.interval}
        )
        settings.ensure_dirs()
    curator = Curator(settings)
    curator.run_daemon(once=args.once)


if __name__ == "__main__":
    main()
