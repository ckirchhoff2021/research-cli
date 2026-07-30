你是技能优化专家。请分析以下失败案例，指出当前技能的不足，并提出具体的编辑建议。

## 当前技能文档
{}

## 历史被拒编辑（避免重复）
{}

## 失败案例分析
{}

## 任务要求
请分析这些失败案例的共同模式，提出针对当前技能的编辑建议。
编辑建议应优先修复会导致任务失败、误触发、漏步骤、错误工具调用或输出不符合预期的问题。

每个编辑建议必须使用以下格式之一：
- append: 在文档末尾追加新规则
- insert_after: 在指定锚点文本后插入新内容
- replace: 替换指定范围的文本
- delete: 删除指定范围的文本

请按以下格式输出：
```
<patch>
<edit op="append">
<anchor>N/A</anchor>
<content>要追加的内容</content>
</edit>
<edit op="insert_after">
<anchor>锚点文本（需要匹配的原文）</anchor>
<content>要插入的内容</content>
</edit>
<edit op="replace">
<target>要替换的原文</target>
<content>替换后的内容</content>
</edit>
<edit op="delete">
<target>要删除的原文</target>
</edit>
<edit_reason>编辑原因说明</edit_reason>
</patch>
```
只输出结构化编辑，不要输出完整文档。
每个 `<patch>` 需要包含 op、anchor/target、content，以及 1 个对应的 `<edit_reason>`。
最多输出 5 个 `<patch>` 块。
