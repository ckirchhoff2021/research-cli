---
name: markdown-to-html
description: 将文本/Markdown内容转换为美观的HTML文件，支持水墨画、简约现代、学术论文、国风宣纸、科技极简等多种风格
category: productivity
version: 1.0.0
author: ckirchhoff
tags:
  - markdown
  - html
  - 文档转换
  - 样式美化
---

# Markdown/文本转精美HTML技能

## 功能特性
- ✅ 支持标准Markdown语法转换（标题、列表、代码块、表格、图片、链接、引用等）
- ✅ 支持纯文本自动格式化
- ✅ 多种内置风格模板：
  - `ink-wash`：中国风水墨画风格，宣纸纹理、毛笔字体、水墨元素装饰
  - `modern`：简约现代风格，扁平化设计、清晰层级、响应式布局
  - `academic`：学术论文风格，规范排版、适合技术文档/论文
  - `xuan-paper`：国风宣纸风格，淡黄底色、竖排选项、古典边框
  - `tech-minimal`：科技极简风格，暗色主题、代码高亮、适合技术文档
  - `elegant`：优雅印刷风格，衬线字体、适合散文/随笔类内容
- ✅ 自动生成目录导航
- ✅ 代码块语法高亮
- ✅ 数学公式支持（LaTeX）
- ✅ 响应式设计，适配移动端/桌面端
- ✅ 支持自定义标题、作者、日期等元信息
- ✅ 输出单文件HTML，所有资源内联，可直接打开分享

## 依赖环境
- Python >= 3.8
- 依赖包：markdown, pygments, python-frontmatter, jinja2

## 安装依赖
```bash
pip install markdown pygments python-frontmatter jinja2
```

## 使用方法
### 基础命令
```bash
python scripts/convert.py <输入文件路径> [选项]
```

### 选项参数
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o, --output` | 输出HTML文件路径 | 输入文件名.html |
| `-s, --style` | 风格模板，可选值：ink-wash/modern/academic/xuan-paper/tech-minimal/elegant | `modern` |
| `-t, --title` | 文档标题 | 自动从Markdown一级标题提取 |
| `-a, --author` | 文档作者 | 空 |
| `-d, --date` | 文档日期 | 当前日期 |
| `--toc` | 生成目录导航 | 默认开启 |
| `--no-toc` | 不生成目录 | - |
| `--math` | 启用LaTeX数学公式支持 | 默认开启 |

### 使用示例
1. 转换Markdown为水墨风格HTML：
```bash
python scripts/convert.py examples/sample.md -s ink-wash -o output/ink-wash-demo.html
```

2. 转换纯文本为学术风格：
```bash
python scripts/convert.py readme.txt -s academic -t "项目说明文档" -a "陈祥"
```

3. 批量转换目录下所有md文件：
```bash
for f in docs/*.md; do python scripts/convert.py "$f" -s modern -o "output/$(basename "$f" .md).html"; done
```

## 风格说明
### 1. 水墨画风格 (ink-wash)
- 背景：水墨纹理+宣纸质感
- 字体：书法字体优先， fallback到系统衬线字体
- 装饰：水墨山水边角装饰、墨点分隔线
- 适合场景：国风内容、散文、古诗词、文化类文档

### 2. 简约现代风格 (modern)
- 背景：纯白/浅灰渐变
- 字体：无衬线字体，清晰易读
- 装饰：简约卡片阴影、柔和配色
- 适合场景：通用文档、技术说明、产品介绍

### 3. 学术论文风格 (academic)
- 背景：纯白
- 字体：Times New Roman类衬线字体
- 排版：严格的学术排版规范，参考文献格式支持
- 适合场景：学术论文、技术报告、研究文档

### 4. 国风宣纸风格 (xuan-paper)
- 背景：淡黄宣纸纹理，轻微做旧效果
- 可选竖排排版
- 装饰：古典边框、印章元素
- 适合场景：古文、书法作品、传统内容

### 5. 科技极简风格 (tech-minimal)
- 背景：深色主题（暗灰/黑色）
- 字体：等宽+无衬线组合
- 代码高亮：Monokai配色
- 适合场景：技术文档、代码说明、API文档

### 6. 优雅印刷风格 (elegant)
- 背景：米白色
- 字体：优雅衬线字体，适合长文阅读
- 排版：宽松行高、舒适字间距
- 适合场景：散文、随笔、小说、长篇文章

## 目录结构
```
markdown-to-html/
├── SKILL.md              # 技能说明文档
├── scripts/
│   └── convert.py        # 核心转换脚本
├── templates/            # 风格模板目录
│   ├── base.html         # 基础模板
│   ├── ink-wash.html     # 水墨画风格模板
│   ├── modern.html       # 现代风格模板
│   ├── academic.html     # 学术风格模板
│   ├── xuan-paper.html   # 宣纸风格模板
│   ├── tech-minimal.html # 科技极简模板
│   └── elegant.html      # 优雅印刷模板
├── assets/               # 静态资源（内联到HTML中）
│   ├── styles/           # 各风格CSS样式
│   └── fonts/            # 字体资源
└── examples/             # 示例文件
    └── sample.md         # 示例Markdown文件
```

## 注意事项
- 输出为单文件HTML，所有CSS、字体、JS都内联，无需额外依赖
- 图片如果是本地路径会保持相对路径，建议将HTML和图片放在同一目录
- 大文件转换（>10MB）可能需要几秒时间，请耐心等待
- 数学公式渲染使用KaTeX，离线环境也可正常显示

## 自定义扩展
如需新增风格，只需在`templates/`目录下添加新的HTML模板，在`assets/styles/`中添加对应CSS，然后在`convert.py`的STYLES列表中注册即可。
