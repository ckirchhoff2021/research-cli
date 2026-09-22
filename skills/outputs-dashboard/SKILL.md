---
name: outputs-dashboard
description: 为 outputs 或任意目录启动离线可视化画廊，实时扫描并按知识库分类展示视频、图片、绘本、报告、网页、音频、代码与数据，支持文件预览、跳转与增量自动发现。当用户想浏览/展示/盘点 outputs 目录内容、生成离线作品网站时使用。
metadata:
  short-description: 离线目录画廊与作品库
---

# Outputs Dashboard

把一个内容目录（默认仓库的 `outputs/`）变成美观的本地离线网站：服务端实时递归扫描目录，前端按「知识库分类 → 项目目录 → 文件类型 → 文件预览」组织，新增文件后刷新或自动同步即可出现，不需要重新生成 HTML。

## 启动

```bash
.venv/bin/python skills/outputs-dashboard/scripts/server.py
```

常用参数：

- `--root <目录>`：浏览任意目录，默认仓库 `outputs/`
- `--port <端口>`：默认 8765，被占用时自动向后寻找可用端口，实际地址以终端输出为准
- `--no-open`：不自动打开浏览器
- `--build-cache`：预生成全部摘要缓存后退出（适合在空闲时执行）

示例：

```bash
.venv/bin/python skills/outputs-dashboard/scripts/server.py --port 8876
.venv/bin/python skills/outputs-dashboard/scripts/server.py --root /path/to/folder --no-open
```

## 功能与浏览结构

- 主页：统计信息、优质内容、知识库分类入口、跨分类内容类型标签与最近项目。
- 知识库分类页：按目录物理结构展示（如 `01_视频创作`），每个项目以封面与缩略图卡片呈现。
- 内容类型标签：跨分类浏览视频、图片、绘本、报告、网页、音频、小说、数据、代码。
- 项目页：封面/主视频/网页入口、内容统计、图片墙、视频墙、文档、代码功能卡与文件目录树。
- 文件页：图片灯箱与左右切换、视频/音频播放、HTML 沙箱预览、Markdown 渲染、代码高亮。
- 快捷键：`/` 聚焦搜索，`Esc` 清空搜索；灯箱内 `← →` 切换、`Esc` 关闭；右下角有回到顶部按钮。

## 关键约定

- 只监听 `127.0.0.1`，不暴露到局域网；不修改任何被浏览的原始文件。
- 摘要缓存写入目标目录根部的隐藏文件 `.dashboard-cache.json`（扫描自动跳过隐藏文件），按文件 mtime+size 失效；删除该文件即可完全重建缓存。
- 扫描自动跳过符号链接与 `_dashboard` 遗留目录，避免内容重复。
- 页面资源（`index.html`、`app.js`、`styles.css`）位于本技能的 `assets/`，由服务端直接提供。
