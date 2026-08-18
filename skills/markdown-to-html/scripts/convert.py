#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown/文本转精美HTML转换工具
支持多种风格：水墨风、现代风、学术风、宣纸风、科技极简、优雅印刷
"""
import os
import re
import argparse
import datetime
from pathlib import Path
import markdown
from pygments.formatters import HtmlFormatter
from jinja2 import Environment, FileSystemLoader

# 支持的风格列表
STYLES = ["ink-wash", "modern", "academic", "xuan-paper", "tech-minimal", "elegant", "tech-doc"]
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
ASSETS_DIR = BASE_DIR / "assets"

class MarkdownToHTML:
    def __init__(self, style="modern", title=None, author=None, date=None, toc=True, math=True):
        self.style = style if style in STYLES else "modern"
        self.title = title
        self.author = author
        self.date = date or datetime.datetime.now().strftime("%Y-%m-%d")
        self.toc = toc
        self.math = math
        
        # 初始化Jinja2环境
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
        
        # Markdown扩展配置
        self.md_extensions = [
            "extra",
            "tables",
            "fenced_code",
            "codehilite",
            "toc",
            "footnotes",
            "attr_list",
            "md_in_html"
        ]
        self.md_extension_configs = {
            "codehilite": {
                "css_class": "highlight",
                "linenums": False,
                "guess_lang": True
            },
            "toc": {
                "permalink": False,
                "toc_depth": "2-4"
            }
        }
    
    def _read_file(self, file_path):
        """读取输入文件内容，支持md/txt格式"""
        file_path = Path(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 如果是纯文本，转换为Markdown格式
        if file_path.suffix == ".txt":
            content = self._text_to_markdown(content)
        
        # 如果未指定标题，从Markdown提取一级标题
        if not self.title:
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            self.title = title_match.group(1).strip() if title_match else file_path.stem
        
        return content
    
    def _text_to_markdown(self, text):
        """纯文本转Markdown格式"""
        lines = text.split("\n")
        md_content = []
        for line in lines:
            line = line.strip()
            if not line:
                md_content.append("")
                continue
            # 检测可能的标题（短行，结尾无标点）
            if len(line) < 30 and not re.search(r"[。，！？,.!?]$", line) and not line.startswith(("-", "*", "1.", "2.", "3.")):
                md_content.append(f"## {line}")
            else:
                md_content.append(line)
        return "\n".join(md_content)
    
    def _get_style_css(self):
        """读取对应风格的CSS内容"""
        css_path = ASSETS_DIR / "styles" / f"{self.style}.css"
        if not css_path.exists():
            css_path = ASSETS_DIR / "styles" / "modern.css"
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        # 添加代码高亮CSS
        if self.style in ["tech-minimal", "tech-doc"]:
            formatter = HtmlFormatter(style="monokai")
        else:
            formatter = HtmlFormatter(style="default")
        css += f"\n{formatter.get_style_defs('.highlight')}"
        return css
    
    def _get_math_js(self):
        """获取KaTeX数学公式支持的JS（内联）"""
        if not self.math:
            return ""
        # 内联KaTeX CDN链接，离线环境可替换为本地路径
        return """
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
            onload="renderMathInElement(document.body, {delimiters: [{left: '$$', right: '$$', display: true},{left: '$', right: '$', display: false}]});"></script>
        """
    
    def _protect_math(self, text):
        """转换前提取数学公式，防止Markdown解析器破坏公式内容"""
        self._math_store = []
        def _save(m):
            idx = len(self._math_store)
            self._math_store.append(m.group(0))
            return f"\x00MATH{idx}\x00"
        # 先保护块级公式$$...$$，再保护行内$...$
        text = re.sub(r'\$\$(.+?)\$\$', _save, text, flags=re.DOTALL)
        text = re.sub(r'\$([^$\n]+?)\$', _save, text)
        return text

    def _restore_math(self, html):
        """转换后恢复数学公式"""
        def _load(m):
            idx = int(m.group(1))
            return self._math_store[idx]
        return re.sub(r'\x00MATH(\d+)\x00', _load, html)

    def _ensure_table_blank_lines(self, text):
        """确保表格前后有空行，避免表格被并入段落"""
        lines = text.split('\n')
        result = []
        for i, line in enumerate(lines):
            is_table = line.strip().startswith('|')
            prev_is_table = i > 0 and lines[i-1].strip().startswith('|')
            if is_table and not prev_is_table and i > 0 and lines[i-1].strip():
                result.append('')  # 表格前加空行
            result.append(line)
            if is_table and i + 1 < len(lines) and lines[i+1].strip() and not lines[i+1].strip().startswith('|'):
                result.append('')  # 表格后加空行
        return '\n'.join(result)

    def convert(self, input_path, output_path=None):
        """执行转换"""
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        
        # 确定输出路径
        if not output_path:
            output_path = input_path.with_suffix(".html")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取并转换内容
        content = self._read_file(input_path)
        # 预处理：保护数学公式 + 修复表格空行
        content = self._protect_math(content)
        content = self._ensure_table_blank_lines(content)
        md = markdown.Markdown(extensions=self.md_extensions, extension_configs=self.md_extension_configs)
        html_content = md.convert(content)
        # 后处理：恢复数学公式
        html_content = self._restore_math(html_content)
        toc_html = md.toc if self.toc else ""
        
        # 加载模板
        template = self.env.get_template(f"{self.style}.html")
        css_content = self._get_style_css()
        math_js = self._get_math_js()
        
        # 渲染HTML
        final_html = template.render(
            title=self.title,
            author=self.author,
            date=self.date,
            content=html_content,
            toc=toc_html,
            css=css_content,
            math_js=math_js,
            style=self.style
        )
        
        # 写入输出文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        
        print(f"✅ 转换成功！输出文件: {output_path.resolve()}")
        print(f"📄 标题: {self.title}")
        print(f"🎨 风格: {self.style}")
        return str(output_path.resolve())

def main():
    parser = argparse.ArgumentParser(description="Markdown/文本转精美HTML工具")
    parser.add_argument("input", help="输入文件路径（.md或.txt）")
    parser.add_argument("-o", "--output", help="输出HTML文件路径")
    parser.add_argument("-s", "--style", default="modern", choices=STYLES, help="风格模板，默认modern")
    parser.add_argument("-t", "--title", help="文档标题，默认自动提取")
    parser.add_argument("-a", "--author", help="文档作者")
    parser.add_argument("-d", "--date", help="文档日期，默认当前日期")
    parser.add_argument("--toc", action="store_true", default=True, help="生成目录")
    parser.add_argument("--no-toc", action="store_false", dest="toc", help="不生成目录")
    parser.add_argument("--math", action="store_true", default=True, help="支持数学公式")
    parser.add_argument("--no-math", action="store_false", dest="math", help="不支持数学公式")
    
    args = parser.parse_args()
    
    converter = MarkdownToHTML(
        style=args.style,
        title=args.title,
        author=args.author,
        date=args.date,
        toc=args.toc,
        math=args.math
    )
    
    converter.convert(args.input, args.output)

if __name__ == "__main__":
    main()
