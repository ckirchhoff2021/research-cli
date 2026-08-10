---
name: web-crawler
description: 网页扒取与话题资料采集专业技能，支持三种模式：抓取单个网页的标题/正文/链接、从种子 URL 出发同域深度爬取、按话题关键词自动搜索全网相关页面并整理成资料报告。当用户要求扒取网页、爬取网站、抓取网页内容、采集某个话题的资料、收集某主题的文献素材、把某个网站的内容保存下来、调研某个话题时必须使用本技能，即使用户没有明确说"爬虫"二字，只要需求本质是"从网页获取内容并整理"也要触发。
---

# Web Crawler 技能

网页内容扒取与话题资料采集技能。内置核心爬虫脚本（仅依赖 requests + beautifulsoup4），提供三种模式，覆盖"给一个网址抓内容"和"给一个话题找资料"两类需求。

## 核心能力

| 模式 | 适用场景 | 输入 | 输出 |
|------|---------|------|------|
| `fetch` | 抓取单个网页 | URL | 标题 + 正文 + 链接（Markdown + JSON） |
| `crawl` | 同域深度爬取（站内多页） | 种子 URL + 深度/页数 | 逐页正文 + 索引 |
| `topic` | 按话题自动搜索并采集 | 话题关键词 | 来源清单 + 各页正文的资料包 |

所有输出统一写入项目根目录 `outputs/web-crawler/` 下。

## 使用流程

### 1. 判断模式

- 用户给了**具体 URL**，只要这一个页面的内容 → `fetch`
- 用户给了 URL，想要**整个站点/栏目**的内容 → `crawl`
- 用户只给了**话题/关键词**，没有 URL → `topic`

### 2. 执行脚本

统一入口（用项目 venv 的 python）：

```bash
# 单页抓取
.venv/bin/python skills/web-crawler/scripts/crawler.py fetch --url "<URL>"

# 同域深度爬取（默认 10 页、深度 2）
.venv/bin/python skills/web-crawler/scripts/crawler.py crawl --url "<种子URL>" --max-pages 10 --max-depth 2

# 话题资料采集（默认抓 8 条搜索结果）
.venv/bin/python skills/web-crawler/scripts/crawler.py topic --query "<话题关键词>" --count 8
```

脚本 stdout 输出 JSON 摘要（含输出目录路径），stderr 输出进度日志。

### 3. 参数说明

| 参数 | 适用模式 | 说明 | 默认值 |
|------|---------|------|--------|
| `--url` | fetch/crawl | 目标 URL（crawl 为种子） | 必填 |
| `--query` | topic | 话题关键词 | 必填 |
| `--count` | topic | 搜索结果条数上限 | 8 |
| `--max-pages` | crawl | 最多抓取页数 | 10 |
| `--max-depth` | crawl | 最大链接深度（种子为 0） | 2 |
| `--delay` | crawl/topic | 请求间隔秒数（含随机抖动） | 1.0 / 1.5 |
| `--out` | 全部 | 自定义输出目录 | `outputs/web-crawler/<任务名>` |
| `--cookie` | 全部 | 登录态 Cookie（全局参数，放在子命令前） | 无 |
| `--ignore-robots` | 全部 | 跳过 robots.txt 检查（需用户明确知情同意） | 关闭 |

### 4. 整理资料（关键步骤）

脚本只负责"抓"，**整理成用户要的报告由你完成**：

- `fetch`：读取输出目录的 `page.md`，按用户需求摘要/翻译/提炼
- `crawl`：读取 `index.md` 了解全貌，按需读取 `pages.json` 中的具体页面
- `topic`：读取 `digest.md`（含来源清单 + 各页正文），然后：
  1. 提炼各来源的核心观点
  2. 归纳共识与分歧
  3. 输出一份结构化的话题调研报告（Markdown），附来源链接
  4. 报告保存到 `outputs/web-crawler/topic_<关键词>/report.md`

### 5. 向用户汇报

必须包含：
1. 抓取结果概览（成功/失败数量）
2. 整理后的内容（摘要或完整报告）
3. 输出文件的绝对路径
4. 失败项的原因说明（如 robots 禁止、403 反爬）

## 内置机制说明

- **合规默认**：默认遵守 robots.txt；请求间隔带随机抖动；UA 伪装为常见浏览器
- **搜索容错**：topic 模式对中文多词查询自动生成多个变体（加引号/截断/去空格），并按关键词重合度打分排序，过滤拆词降级产生的无关结果
- **站点回退**：知乎专栏（zhuanlan.zhihu.com）403 时自动转用 tardis 镜像抓取
- **正文提取**：优先 `<article>`/`<main>` 标签，否则取文本最长的 div；自动剥离导航/脚本等噪音
- **断点信息**：每次任务的 JSON 摘要都含输出目录，失败重跑可指定 `--out` 覆盖

## 示例

### 示例 1：抓取单个网页
**用户输入**：帮我扒一下 https://example.com 这个页面
**执行**：
```bash
.venv/bin/python skills/web-crawler/scripts/crawler.py fetch --url "https://example.com"
```
**输出**：向用户展示标题、正文摘要，并给出 `page.md` 路径。

### 示例 2：按话题采集资料
**用户输入**：帮我收集一下大模型 RAG 技术的资料，整理个报告
**执行**：
```bash
.venv/bin/python skills/web-crawler/scripts/crawler.py topic --query "大模型 RAG 检索增强生成" --count 8
```
**后续**：读取 `digest.md`，整理成话题调研报告保存为 `report.md`，向用户汇报核心发现 + 来源清单。

### 示例 3：需要登录态的站点
**用户输入**：帮我抓知乎某篇文章，我有账号
**执行**：先请用户提供浏览器 Cookie（F12 → Network → 复制 Cookie 头），然后：
```bash
.venv/bin/python skills/web-crawler/scripts/crawler.py --cookie "<cookie>" fetch --url "<URL>" --ignore-robots
```
注意：`--ignore-robots` 使用前必须向用户说明该站点 robots.txt 的限制并获得确认。

## 注意事项

1. **不要破解反爬**：遇到 403/验证码/加密签名，如实报告失败原因，不要尝试逆向反爬机制
2. **控制规模**：crawl 默认 10 页已足够多数场景；用户要大规模抓取时先确认目标站点承受能力
3. **隐私合规**：不采集个人隐私数据（手机号、住址等）；话题报告引用内容时保留来源链接
4. **动态页面**：脚本只处理服务端渲染的 HTML；若页面内容靠 JS 加载（抓到的正文为空），告知用户需要浏览器方案（Playwright），不要反复重试
