# Mermaid 图使用与排错

在中文技术报告 / README 中，**优先使用 Mermaid 流程图，不要手写 ASCII 框图**。
原因：CJK 字符在等宽字体下占 2 列，空格/半角符号占 1 列，靠补空格对齐几乎不可能在所有渲染器（GitHub/GitLab/VS Code/Terminal）下保持一致；Mermaid 渲染为矢量 SVG，天然对齐且支持配色。

## Mermaid 语法坑点（2026-08 实测，mermaid 10.9.8）

| 坑 | 错误写法 | 正确写法 |
|---|---|---|
| 中文子图 ID 不能裸用 | `subgraph 飞书 ... end` | `subgraph FS[飞书] ... end`（给 ASCII ID + 中文标签） |
| 节点标签含特殊字符必须加引号 | `A[FeishuTagBot<br/>client]` | `A["FeishuTagBot<br/>client"]` |
| HTML 实体在节点文本里失效 | `&lt;chat_id&gt;` | 用方括号 `[chat_id]` 或反引号 `` `chat_id` `` |
| style 引用不存在的节点 ID → 整体解析失败 | `style X1 fill:...` 但 X1 未定义 | style 前检查所有 ID 都在图中出现过 |
| 边标签与中文间空格 | 可正常使用 | `A -->|标签| B` 中英文都可以 |
| `·` 中点、`…` 省略号在标签里可用 | — | 直接用 |
| `<br/>` 换行必须是 XHTML 自闭合 | `<br>` 可能不解析 | 用 `<br/>` |
| subgraph 内必须放至少一个节点 | 空 subgraph 有时报错 | 放一个占位节点或删除 |

## 排错流程（Mermaid "Syntax error in text" 不给行号）

1. 把 Mermaid 代码写入独立 HTML（参考 `architecture-diagram` 模板的单文件结构），用 `browser_navigate` + `browser_vision` 验证
2. **二分法定位**：注释掉后半段图，看是否渲染；逐步还原到找到出错节点/连线
3. 常见触发：未引用的 style、中文裸 ID、未闭合引号、`<br>` 非自闭合
4. 修复后 `browser_vision` 确认无重叠/裁剪/颜色问题再写入最终文档

## 适用场景选择

| 图类型 | 推荐工具 |
|-------|---------|
| 系统架构/部署/基础设施暗色图 | `architecture-diagram`（SVG+暗色网格，最专业） |
| README 内简单流程图/时序图/状态图 | Mermaid（GitLab/GitHub 原生渲染，零依赖） |
| 手绘风格/头脑风暴 | `excalidraw` |
| 数学/算法流程图 | Mermaid + LaTeX（数学公式用 `$...$`） |

## README 中的 Mermaid vs ASCII 决策

- **中文项目 README**：永远用 Mermaid，不要用 ASCII 框图。CJK 双宽字符会让 ASCII 框图在不同字体/渲染器下错位。
- **英文项目 README**：简单流程可 ASCII（所有字符等宽），复杂图仍建议 Mermaid。
- **技术报告 HTML**：优先用 `architecture-diagram` 生成独立暗色 SVG，通过 `<iframe>` 嵌入；Mermaid 可作为正文内小图的补充。
