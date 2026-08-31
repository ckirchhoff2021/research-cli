---
name: md2html
description: 把 Markdown 或纯文本渲染为排版精美、赏心悦目的独立 HTML 文件，内置水墨、工笔重彩、电影写实、黑白版画、民国纸笺、现代简约 6 套视觉风格，支持目录、表格、代码块、脚注、任务列表、打印友好。当用户要求把 markdown/文本/笔记/文章转成 HTML、做漂亮的网页版排版、给文档换个好看的样式、生成可分享的 HTML 页面时必须使用本技能，即使用户没有明确说"HTML"，只要需求本质是"文本内容 → 美观的可浏览页面"也要触发。
---

# md2html — 文本/Markdown 转精美 HTML

把一份 Markdown（或纯文本）渲染成**单文件、零依赖、可直接双击打开**的美观 HTML。
内置 6 套视觉风格，全部通过 CSS 变量驱动，改 `:root` 即可整体换肤。

## 触发条件
- 把 markdown / txt / 笔记 / 文章转成 HTML 或网页
- 给已有文档做"好看的排版"、"精美渲染"、"赏心悦目的页面"
- 生成可分享、可打印的静态页面

## 关键路径（本机）
- 转换脚本：`scripts/md2html.py`（依赖 `markdown` 库）
- 样式表：`templates/styles.css`（6 套主题 + 全部组件样式，带注释）
- 示例文档：`examples/sample.md`（覆盖标题/表格/代码/脚注/任务列表等全组件）
- 输出目录：`<project-root>/outputs/`（遵循项目规范，勿散落在别处）

## 工作流（3 步）

### 1. 确认输入与风格
- 输入是文件路径还是直接粘贴的文本？粘贴文本先写入 `outputs/<slug>.md` 再转换。
- 风格未指定时**主动询问**，给出选项：
  水墨（默认）/ 工笔重彩 / 电影写实 / 黑白版画 / 民国纸笺 / 现代简约。
  内容偏古典人文 → 水墨/工笔/民国；科技商业 → 现代简约；暗色沉浸 → 电影写实。

### 2. 执行转换
```bash
uv run --with markdown <skill>/scripts/md2html.py <输入.md> \
  --style ink -o <project-root>/outputs/<slug>.html
```
- 项目 `.venv` 未装 markdown 库，用 `uv run --with markdown` 免安装运行；
  若已 `pip install markdown`，直接 `.venv/bin/python` 运行亦可。
- 常用选项：
  - `--title "标题" --subtitle "副标题"`：输入无一级标题时手动指定（有 H1 会自动提取为 `<title>`）
  - `--toc`：文首插入目录（收录 h2/h3，`--toc-depth 1-3` 可调层级）
  - `--no-footer`：去掉页脚版权行
  - `--open`：生成后自动用浏览器打开（macOS）
  - `--css <path>`：换自定义样式表；`--link-css` 外链模式便于调试
- 长文档建议加 `--toc`；多文档批量转换时循环调用即可，脚本为无状态纯转换。

### 3. 验证（不可省）
1. `read_file` 打开生成的 HTML，确认：`data-theme` 与所选风格一致、正文内容完整、
   `<title>` 正确、表格/代码块/脚注结构存在。
2. 有条件时用无头浏览器截图目检视觉效果：
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --headless --screenshot=/tmp/preview.png --window-size=1000,2400 \
     --hide-scrollbars "file://<绝对路径>.html"
   ```
   再 `read_file` 多模态查看截图，确认配色、字体、留白符合所选风格。

## 风格速查

| --style | 中文名 | 气质 | 适用内容 |
|---------|--------|------|----------|
| ink | 水墨 | 宣纸底·宋体·朱砂印章色 | 古典人文、历史、文学 |
| gongbi | 工笔重彩 | 暖纸·楷体·金红 | 传统艺术、民俗、节庆 |
| cinema | 电影写实 | 深底·黑体·金蓝 | 影评、深度报道、沉浸阅读 |
| woodcut | 黑白版画 | 灰白·宋体·纯黑白 | 严肃论述、版画风配图 |
| zhiqing | 民国纸笺 | 旧纸·楷体·藏青 | 书信、回忆录、近代史 |
| modern | 现代简约 | 白底·黑体·靛蓝 | 技术文档、报告、商业 |

## 自定义风格
改 `templates/styles.css` 中对应主题的 `:root` 变量即可整体换肤（15+ 变量：
底色/正文/强调/卡片/引用/表头/代码/字体等）。新增主题：复制一个 `:root[data-theme="xxx"]`
块，并在脚本 `STYLE_NAMES` 字典注册中文名。

## Pitfalls
- **markdown 库未安装**：项目 `.venv` 默认没有，务必用 `uv run --with markdown` 或先安装；
  脚本检测到缺失会打印明确指引并退出。
- **相对图片路径**：HTML 输出到 outputs/ 后，文中的相对图片路径以 HTML 所在目录为基准，
  图片需一并复制过去，否则裂图。
- **`--title` 与原文 H1 重复**：指定 `--title` 时脚本会在顶部插入大标题，
  若原文首行也是 `# 标题` 会出现双标题——二选一，或让原文从二级标题开始。
- **外链 CSS（--link-css）不是单文件**：分享给他人时去掉该选项，用默认内嵌模式。
- **打印**：已内置 @media print 优化（白底、链接附 URL、避免跨页截断），直接浏览器打印即可。
