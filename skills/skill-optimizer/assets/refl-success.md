你是技能优化专家。请分析以下成功案例，总结当前技能做对了什么，并提出应当保留或强化的编辑建议。

## 当前技能文档
{}

## 历史被拒编辑（避免重复）
{}

## 成功案例分析
{}

## 任务要求
请分析这些成功案例的共同模式，找出当前技能中有效的规则、流程或表达，并提出针对当前技能的编辑建议。
编辑建议的目标应是：
- 保留已经有效的规则，避免后续重写破坏现有正确行为
- 将隐含但有效的做法补充为更明确的规则
- 提升成功模式的可复用性和稳定性

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
编辑建议应以“保留和强化成功模式”为主，不要把成功案例错误改写成失败修复建议。
最多输出 5 个 `<patch>` 块。
