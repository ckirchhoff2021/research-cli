#!/usr/bin/env python3
"""md2html — 把 Markdown/纯文本渲染为美观的多风格 HTML。

用法示例：
    # 最简：水墨风（默认），输出到同名 .html
    python md2html.py 文章.md

    # 指定风格与输出路径
    python md2html.py 文章.md --style cinema -o outputs/文章.html

    # 无标题的片段文本：手动指定标题 + 生成目录
    python md2html.py notes.md --title "会议纪要" --subtitle "2026-04" --toc

依赖：仅需 `markdown` 库。未安装时可用 uv 免安装运行：
    uv run --with markdown scripts/md2html.py 文章.md --style gongbi

风格（--style）：
    ink      水墨（默认）：宣纸底 · 宋体 · 朱砂点缀
    gongbi   工笔重彩：暖纸 · 楷体 · 金红
    cinema   电影写实：深底 · 黑体 · 金蓝
    woodcut  黑白版画：灰白 · 宋体 · 纯黑白
    zhiqing  民国纸笺：旧纸 · 楷体 · 藏青
    modern   现代简约：白底 · 黑体 · 靛蓝
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

STYLE_NAMES = {
    "ink": "水墨",
    "gongbi": "工笔重彩",
    "cinema": "电影写实",
    "woodcut": "黑白版画",
    "zhiqing": "民国纸笺",
    "modern": "现代简约",
}

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSS = SKILL_ROOT / "templates" / "styles.css"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN" data-theme="{style}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<div class="doc">
{title_block}{toc_block}{body}
{footer_block}</div>
</body>
</html>
"""


def import_markdown():
    try:
        import markdown  # noqa: PLC0415
        return markdown
    except ImportError:
        sys.exit(
            "错误：缺少 markdown 库。请先安装（pip install markdown），"
            "或用 uv 免安装运行：\n"
            "  uv run --with markdown " + " ".join(sys.argv)
        )


def extract_first_h1(md_text: str) -> str | None:
    """从 markdown 源码提取第一个一级标题文本（用于 <title> 与页脚）。"""
    for line in md_text.splitlines():
        m = re.match(r"^#\s+(.+?)\s*#*\s*$", line)
        if m:
            return m.group(1).strip()
    return None


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def render_task_lists(html: str) -> str:
    """把 `- [ ] / - [x]` 渲染为样式化复选框（python-markdown 无内置 task list 扩展）。

    先替换 li 内的 [ ]/[x] 文本为 <input type="checkbox">，
    再给首项即任务项的 <ul> 加 task-list 类以套用样式。
    """
    html = re.sub(
        r"<li>\[\s\]\s*", '<li><input type="checkbox" disabled> ', html
    )
    html = re.sub(
        r"<li>\[[xX]\]\s*", '<li><input type="checkbox" checked disabled> ', html
    )
    return re.sub(
        r"<ul>(\s*<li><input type=\"checkbox\")",
        r'<ul class="task-list">\1',
        html,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="把 Markdown/纯文本渲染为多风格美观 HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="风格选项：" + "、".join(f"{k}({v})" for k, v in STYLE_NAMES.items()),
    )
    p.add_argument("input", help="输入的 .md / .markdown / .txt 文件")
    p.add_argument("-o", "--output", help="输出 HTML 路径（默认：输入同名 .html）")
    p.add_argument(
        "--style", choices=sorted(STYLE_NAMES), default="ink",
        help="视觉风格（默认 ink 水墨）",
    )
    p.add_argument("--title", help="文档主标题（输入已含一级标题时可省略）")
    p.add_argument("--subtitle", help="副标题（需配合 --title）")
    p.add_argument("--toc", action="store_true", help="在文首插入目录（h2/h3）")
    p.add_argument("--toc-depth", default="2-3", help="目录收录层级，如 2-3（默认）或 1-3")
    p.add_argument("--no-footer", action="store_true", help="不输出页脚版权行")
    p.add_argument("--css", help="自定义 CSS 文件路径（默认用技能自带 styles.css）")
    p.add_argument(
        "--link-css", action="store_true",
        help="用 <link> 引用 CSS 而非内嵌（便于开发调试，默认内嵌为单文件）",
    )
    p.add_argument("--open", action="store_true", help="生成后用系统浏览器打开")
    return p


def main() -> None:
    args = build_parser().parse_args()
    md_lib = import_markdown()

    src = Path(args.input).expanduser()
    if not src.is_file():
        sys.exit(f"错误：输入文件不存在：{src}")
    text = src.read_text(encoding="utf-8")

    # ---- markdown → HTML ----
    extensions = [
        "extra",        # 表格、围栏代码、脚注、定义列表等常用扩展合集
        "sane_lists",
        "toc",
    ]
    md = md_lib.Markdown(extensions=extensions, extension_configs={
        "toc": {
            "toc_depth": args.toc_depth,
            # 中文标题直接作锚点（如 #缘起），而非默认的 #_1 序号
            "slugify": lambda value, sep: re.sub(
                r"[^\w\u4e00-\u9fff\- ]", "", value, flags=re.UNICODE
            ).strip().replace(" ", sep) or value,
        },
    })
    body_html = render_task_lists(md.convert(text))

    # ---- 标题 ----
    title = args.title or extract_first_h1(text) or src.stem
    title_block = ""
    if args.title:
        title_block = f"<h1>{args.title}</h1>\n"
        if args.subtitle:
            title_block += f'<div class="doc-subtitle">{args.subtitle}</div>\n'

    # ---- 目录 ----
    toc_block = ""
    if args.toc:
        # md.toc 自带 <div class="toc"> 包裹，直接插入，勿再套一层
        toc_html = getattr(md, "toc", "").strip()
        if toc_html:
            toc_block = toc_html + "\n"
        else:
            print("警告：未找到可生成目录的标题（h2/h3），跳过 TOC", file=sys.stderr)

    # ---- 页脚 ----
    footer_block = ""
    if not args.no_footer:
        style_cn = STYLE_NAMES[args.style]
        footer_block = (
            f'<div class="colophon">{title} · {style_cn}风格 · '
            f"由 md2html 生成于 {date.today().isoformat()}</div>\n"
        )

    # ---- CSS ----
    css_path = Path(args.css).expanduser() if args.css else DEFAULT_CSS
    if not css_path.is_file():
        sys.exit(f"错误：CSS 文件不存在：{css_path}")
    css_text = css_path.read_text(encoding="utf-8")
    if args.link_css:
        # 开发模式：外链 CSS（需与输出同目录或用绝对路径）
        css_tag = f'<link rel="stylesheet" href="{css_path}">'
        css_text = ""
    else:
        css_tag = ""

    html = PAGE_TEMPLATE.format(
        style=args.style,
        title=title,
        css=css_text,
        title_block=title_block,
        toc_block=toc_block,
        body=body_html,
        footer_block=footer_block,
    )
    if css_tag:  # 外链模式：把 <link> 插到 <style> 块位置
        html = html.replace("<style>\n\n</style>", css_tag)

    # ---- 输出 ----
    out = Path(args.output).expanduser() if args.output else src.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"✓ 已生成：{out.resolve()}")
    print(f"  风格：{args.style}（{STYLE_NAMES[args.style]}）  大小：{out.stat().st_size / 1024:.1f} KB")

    if args.open:
        import subprocess
        if sys.platform == "darwin":
            subprocess.run(["open", str(out.resolve())], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(out.resolve())], check=False)


if __name__ == "__main__":
    main()
