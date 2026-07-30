你是技能优化专家。以下有多个候选 patch，请按重要性从高到低排序，并只保留前 {0} 个最重要的 patch。

## 当前技能文档
{1}

## 候选 patch
{2}

## 任务要求
1. 按重要性排序（失败驱动的编辑通常更重要）
2. 优先保留能修复关键错误的 patch
3. 避免保留重复或冲突的 patch
4. 每个候选 patch 是一个原子编辑组；选中后必须完整保留其中的全部 `<edit>`，不得拆分或改写
5. 只输出前 {0} 个 patch

请按以下格式输出：
```
<patch>
<edit op="insert_after">
<anchor>锚点文本</anchor>
<content>要插入的内容</content>
</edit>
<edit op="replace">
<target>要替换的原文</target>
<content>替换后的内容</content>
</edit>
<edit_reason>为什么该编辑应优先保留</edit_reason>
</patch>
```
每个保留的原子编辑组输出一个完整的 `<patch>` 块，按重要性从高到低排列。
只输出前 {0} 个 `<patch>` 块，不要输出 `<selected>`、`<rank>` 或其他解释性文字。
