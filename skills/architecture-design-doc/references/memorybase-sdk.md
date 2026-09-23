# MemoryBase (bytedance-memorybase SDK) 能力速查

来源：feishu-claude-tag 项目 `.venv/lib/python3.12/site-packages/bytedance/memorybase/client.py`（SDK 0.6.0 实读）。
内部文档 `cloud.bytedance.net/docs/mem0/...` 需字节 SSO，浏览器不可达——此速查即替代事实源。

## 客户端
- `Memory(server, api_key, timeout, validate_api_key=True, insecure_skip_verify=False)`，别名 `MemoryClient`/`MemoryBaseClient`。
- 鉴权：`Authorization: Token <key>`；`validate_api_key=True` 时构造即 `GET /v1/ping/` 拿 org_id/project_id（metrics 依赖 project_id）。
- **同步 httpx.Client 长连接，禁止跨进程共享**；支持 `with` 上下文。
- 非 2xx 抛 `APIError(status_code, message, detail)`；诊断字段 `last_status_code/last_url/last_method`。
- `_payload` 严格白名单：传未定义参数直接 `ValueError`——升级 SDK 前必回归。

## 长期记忆 /v1/memories/
| 方法 | 要点 |
|---|---|
| `add(messages, user_id=, agent_id=, run_id=, infer=, async_mode=, custom_instructions=, metadata=, no_write=, specified_strategy_names=, builtin_strategy_names=, extract_multimodal_attachments=, prev_job_id=)` | 三级 scope 任意组合；`infer=True` 服务端 LLM 提取+ADD/UPDATE/DELETE/NOOP 整合；`async_mode=True` 返回 event_id；`no_write=True` 只抽取不落库（灰度审计用） |
| `search(query, user_id=, agent_id=, run_id=, top_k=, filters=, search_mode=, rrf_k=)` | 混合检索，`rrf_k` 为 RRF 融合系数 |
| `get_all(user_id=/agent_id=/run_id=, filters=)` | 按 scope 枚举 |
| `get(memory_id)` / `update(memory_id, text=, metadata=)` / `delete(memory_id)` | 单条操作 |
| `get_event(event_id)` | 异步事件轮询；成功态 {COMPLETED, DONE, FINISHED, SUCCEEDED, SUCCESS}，失败态 {CANCELED, ERROR, FAILED, ...} |
| `update_project(project_id, strategies=, llm=)` | 项目级策略定制 |

## 短期记忆 STM /v1/stm/（session/event/message 三层）
- `stm_create_session(agent_id, session_id, user_id=, metadata=)`
- `stm_create_event(agent_id, session_id, messages=[...])` → event_id
- `stm_append_messages(agent_id, session_id, messages, event_id=)`
- `stm_get_latest_messages(agent_id, session_id, n=)`
- list/get/update/delete session 与 event 全套。
- 映射飞书：session=话题(thread)、event=问答轮、messages=OpenAI 格式消息。

## 服务端点
- 生产：`https://mem0-cn.byted.org/bytedance.memorybase.memorybase_cn`
- 试验：`..._playground`
- API Key 只进 `.env`；feishu-claude-tag 的 `tests/test_memo*.py` 有硬编码 key 需清理。

## 方法论锚点（设计文档引用用）
- mem0 管道：提取→整合(ADD/UPDATE/DELETE/NOOP)→检索；论文 arXiv:2504.19413（准确率+26%、延迟−91%、token−90%，数字系知乎转述）。
- 多 Agent 共享治理共识："私有默认、共享显式"（TencentDB Agent Memory 的 ACL 四级可见性）；检索深度与泄露风险正相关（Survey 结论，MEXTRA 攻击）。
