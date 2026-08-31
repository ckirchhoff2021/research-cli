"""coding — 基于 deepagents 的科研 Agent 框架。

模块组成：
- config: 全局配置与环境变量
- session_store: 会话持久化（SQLite）
- subagents: 自定义 SubAgent 定义（deepagents SubAgent 规范）
- agent_factory: Agent 构建工厂（checkpointer 持久化）
- curator: 后台自进化子代理（监视会话 → 沉淀 memory/skills）
- server: FastAPI 服务（SSE 流式 + 会话管理 + 文件预览）
"""

__version__ = "0.1.0"
