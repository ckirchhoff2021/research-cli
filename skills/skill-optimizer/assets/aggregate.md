你是技能优化专家。以下有多个独立生成的编辑建议，请将它们合并为一个连贯的编辑集合。

## 当前技能文档
{}

## 待合并的编辑
{}

## 任务要求
1. 合并重复的编辑
2. 消除冲突的编辑（同一位置的不同编辑，保留更重要的）
3. 合并后保留的编辑必须使用以下格式：
```
<patch>
<edit op="append|insert_after|replace|delete">
<anchor>锚点文本或 N/A</anchor>
<target>要替换/删除的原文（仅replace/delete需要）</target>
<content>编辑内容（仅append/insert_after/replace需要）</content>
</edit>
<edit_reason>合并后保留这些编辑的原因</edit_reason>
</patch>
```
4. 仅将彼此强相关的编辑放入同一个 `<patch>` 块；若原因不同，请拆成多个 `<patch>` 块
5. 每个 `<patch>` 必须包含 1 个 `<edit_reason>`，说明保留该组编辑的原因
只输出 `<patch>` 块，不要输出其他内容。
