# Claude Tag 开源生态快照（2026-08-21 GitHub 实测）

Claude Tag = Anthropic 2026-06-23 发布的 Slack 常驻 AI 同事（闭源、付费、
仅 Claude、仅 Slack）。以下为当日实测的开源替代清单。⚠️ 快照数据，引用前
须重新验证存活（Zilliz Open Tag 即为下线先例）。

## 项目清单（按 stars）

| 项目 | Stars | 定位 |
|---|---|---|
| paradigmxyz/centaur | 1167 | Slack 原生 + 每会话 K8s 沙箱（shell/git/Py/Node/Bun），最完整复刻 |
| CopilotKit/OpenTag | 1107 | MIT，Channels SDK 起步应用，Slack+Teams，含生成式 UI |
| linxidnju/OpenTag | 501 | Apache-2.0，Slack 网关，本地执行+审批+审计轨迹，runtime 可插拔 |
| openma-ai/open-managed-agents | 243 | Apache-2.0，Claude Managed Agents API 开源实现（底座），Anthropic 兼容，CF Workers |
| fancyboi999/open-tag | 164 | 自托管工作区，多引擎（Claude Code/Codex/Copilot） |
| zilliztech/mfs | 121 | MFS 上下文引擎（Milvus 检索，Rust CLI + Py SDK）——Open Tag 的后继底座 |
| AgentBull/ankole | 50 | AI Workforce OS |
| anthropics/claude-tag-plugins | 43 | Anthropic 官方插件仓库 |
| duyet/oma | 5 | drop-in Managed Agents |
| liliang-cn/tagit | 4 | 自托管 Claude Tag |

## 飞书生态（用户日常通道）

- **aws-samples/sample-claude-tag-in-lark**（官方示例）：Bedrock AgentCore +
  Claude Agent SDK，免 Claude 订阅；模型后端三选一（LiteLLM 网关默认 /
  Bedrock Invoke 直连 / Mantle）；@委派+CardKit 流式+每频道自进化记忆。
- **jiangdaxia-AI/open_claude_tag_lark**：飞书群数字员工团队（产品/研发/调度
  角色分工、拆任务、共享记忆），Py3.11+ MIT；1★个人项目需审代码。
- RCliang/open-claude-tag-feishu：更早期，仅参考。

## Zilliz Open Tag 去向

open-tag / open-claude-tag / opentag 三个 URL 变体全 404，组织仓库只剩 mfs。
推断：Open Tag 是展示 MFS 的传播向 demo，使命完成后收编进 MFS（推断，无官方
公告）。详细盘点见 research-cli `outputs/claude-tag-report/Claude-Tag-开源实现盘点.md`。

## 选型速查

复刻完整度 → centaur；多引擎自托管 → fancyboi999/open-tag；Teams/UI →
CopilotKit/OpenTag；审批审计 → linxidnju/OpenTag；API 底座 → openma；
飞书 → aws-samples（规范）；上下文引擎 → zilliztech/mfs。
