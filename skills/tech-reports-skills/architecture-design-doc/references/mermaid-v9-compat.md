# Mermaid v9 渲染兼容性：特殊字符必须加引号

## 背景（本坑来源）
feishu-claude-tag 的 README/docs 里的 Mermaid 图在本地 mmdc（mermaid-cli v10）能正常渲染，
但用户反馈 GitLab 上「无法渲染」。根因：**GitLab / VS Code / 多数 IDE 内嵌的是 mermaid v9**，
其词法器对「未加引号」标签里的部分 Unicode 字符报 `Lexical error: Unrecognized text`，
而 v10 容错更强、直接放行——所以本地 v10 验证会**漏判**。

## 触发矩阵（mermaid v9.4.3 实测，node + jsdom + isomorphic-dompurify 跑 `mermaid.parse`）

| 标签类型 | 内容 | 未加引号 | 加引号 |
|---|---|---|---|
| 边标签 `-->|...|` | `事件·去重`（含 U+00B7） | ❌ FAIL | ✅ OK |
| 边标签 | `@机器人`（含 `@`） | ❌ FAIL | ✅ OK |
| 节点标签 `[...]` | `web_search·Tavily` | ❌ FAIL | ✅ OK |
| 节点标签 | `语义召回 · Reconciler` | ❌ FAIL | ✅ OK |
| 子图标题 `subgraph X[...]` | `四级隔离 → mem0`（含 U+2192） | ❌ FAIL | ✅ OK |
| 子图标题 | `内置工具·@tool` | ❌ FAIL | ✅ OK |
| 边标签 | `（四级隔离）`（全角括号） | ❌ FAIL | ✅ OK |
| 节点标签 | `云端（四级隔离）`（全角括号） | ❌ FAIL | ✅ OK |

**正常（无需引号）**：`*`、`&`、`+`、`/`、`=`、CJK 汉字、`<br/>`。

## 规则
> 标签里只要出现 `·`(U+00B7)、`@`、`→`(U+2192)、全角 `（）` 之一，就给它加引号。
> 边标签：`A -->|"事件·去重"| B`；节点：`A["web_search·Tavily"]`；子图：`subgraph T["内置工具·@tool"]`。

## 权威验证法（v10 通过不代表 GitLab 能过）
```bash
mkdir -p /tmp/mmdtest/m9 && cd /tmp/mmdtest/m9
npm init -y && npm install mermaid@9 jsdom isomorphic-dompurify
```
再写 parse9.mjs（import mermaid + jsdom + isomorphic-dompurify，`mermaid.initialize({securityLevel:'loose'})`，
逐个 `mermaid.parse(block)`），对每个 ```mermaid 代码块跑一遍，v9 全 OK 才算兼容。

三步交叉验证：
1. mermaid v9.4.3 `parse`（GitLab 同源，**必测**，最容易漏的就是它）
2. mermaid v10 `parse`（本地预览）
3. `npx -y @mermaid-js/mermaid-cli@10` 渲染成 SVG（官方渲染器，确认能出图）

## 其他 v9 兼容写法（保留）
- HTML 尖括号在标签里转义：`e:&lt;employee_id&gt;`（而非裸 `<employee_id>`）。
- `<br/>` 换行正常，无需改 `<br>`。
