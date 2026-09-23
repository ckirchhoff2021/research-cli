#!/usr/bin/env python3
"""MD → 暗色主题 HTML 技术报告一键转换。

用法：python3 md2html.py <input.md> <output.html>

会自动：
- 启用 tables/fenced_code/toc markdown 扩展
- 注入 references/report-html-template.md 的暗色 CSS
- 自动生成章节目录 TOC（插入到第一个 </blockquote> 之后）
- 保留 <iframe>/<figure> HTML 标签（用于内嵌架构图）
"""
import sys, re, argparse
from pathlib import Path
import markdown

CSS = """
:root {
  --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3;
  --muted:#8b949e; --accent:#58a6ff; --green:#3fb950; --purple:#bc8cff;
  --amber:#d29922; --rose:#f85149; --cyan:#39c5cf;
}
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--text);
  font-family:-apple-system,"PingFang SC","Noto Sans SC",sans-serif; line-height:1.85; margin:0; }
.container { max-width:960px; margin:0 auto; padding:40px 24px 80px; }
h1 { font-size:30px; margin:0 0 8px; letter-spacing:-0.02em; }
h2 { font-size:22px; margin:56px 0 16px; padding-bottom:8px; border-bottom:1px solid var(--border); }
h3 { font-size:17px; margin:32px 0 12px; color:var(--accent); }
h4 { font-size:15px; margin:20px 0 8px; color:var(--cyan); }
p { margin:12px 0; font-size:15px; }
code { background:#1f2937; padding:2px 6px; border-radius:4px;
  font-family:"JetBrains Mono",Menlo,monospace; font-size:13px; color:var(--cyan); }
pre { background:#0a0e14; border:1px solid var(--border); border-radius:8px;
  padding:16px; overflow-x:auto; margin:14px 0; font-size:13px; line-height:1.6; }
pre code { background:none; padding:0; color:#d1d9e0; }
table { border-collapse:collapse; width:100%; margin:16px 0; font-size:13.5px; }
th,td { border:1px solid var(--border); padding:8px 12px; text-align:left; vertical-align:top; }
th { background:var(--panel); color:var(--accent); white-space:nowrap; }
tr:nth-child(even) td { background:rgba(255,255,255,0.02); }
blockquote { border-left:3px solid var(--accent); padding:8px 18px; margin:16px 0;
  background:var(--panel); border-radius:0 8px 8px 0; color:var(--muted); font-size:14px; }
figure { margin:28px 0; }
figure iframe { width:100%; height:860px; border:1px solid var(--border);
  border-radius:12px; background:#020617; }
figcaption { text-align:center; color:var(--muted); font-size:13px; margin-top:8px; }
.toc { background:var(--panel); border:1px solid var(--border); border-radius:10px;
  padding:20px 28px; margin:24px 0 40px; }
.toc h2 { border:none; margin:0 0 12px; font-size:16px; color:var(--accent); padding:0; }
.toc ol { padding-left:20px; margin:0; }
.toc li { margin:4px 0; font-size:14px; }
.toc a { color:var(--text); text-decoration:none; }
.toc a:hover { color:var(--accent); text-decoration:underline; }
ul, ol { padding-left:24px; }
li { margin:6px 0; font-size:15px; }
strong { color:#fff; }
hr { border:none; border-top:1px solid var(--border); margin:40px 0; }
a { color:var(--accent); }
.footer { text-align:center; color:var(--muted); font-size:12px; margin-top:60px;
  padding-top:20px; border-top:1px solid var(--border); }
"""

def build_toc(html_body: str):
    # markdown lib only emits heading ids with the toc/attr_list extensions;
    # without them we must slugify ourselves (and patch ids into the body).
    headings = re.findall(r'<h2>(.*?)</h2>', html_body)
    items, ids = [], []
    for title in headings:
        clean = re.sub(r'<[^>]+>', '', title)
        hid = re.sub(r'[^\w\u4e00-\u9fff-]+', '-', clean.strip()).strip('-') or f'sec-{len(ids)}'
        ids.append(hid)
        items.append(f'<li><a href="#{hid}">{clean}</a></li>')
    idx = 0
    def _inject(m):
        nonlocal idx
        hid = ids[idx]; idx += 1
        return f'<h2 id="{hid}">'
    patched = re.sub(r'<h2>', _inject, html_body)
    toc = '<nav class="toc"><h2>目录</h2><ol>' + ''.join(items) + '</ol></nav>'
    return toc, patched

def convert(md_text: str, title: str = "技术报告", footer: str = "") -> str:
    body = markdown.markdown(md_text, extensions=['tables','fenced_code'], output_format='html5')
    toc, body = build_toc(body)
    body = re.sub(r'(</blockquote>)', r'\1' + toc, body, count=1, flags=re.S)
    if not footer:
        from datetime import date
        footer = f"{title} · {date.today().isoformat()} · Research Report"
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title><style>{CSS}</style></head>
<body><div class="container">{body}
<p class="footer">{footer}</p>
</div></body></html>"""

def main():
    ap = argparse.ArgumentParser(description="MD → 暗色技术报告 HTML")
    ap.add_argument("input", help="输入 .md 文件路径")
    ap.add_argument("output", nargs="?", help="输出 .html 文件（默认同名 .html）")
    ap.add_argument("--title", default="技术报告", help="HTML <title>")
    args = ap.parse_args()
    src = Path(args.input)
    dst = Path(args.output) if args.output else src.with_suffix('.html')
    md_text = src.read_text(encoding='utf-8')
    html = convert(md_text, title=args.title)
    dst.write_text(html, encoding='utf-8')
    print(f"✓ {src} → {dst} ({len(html)} bytes)")

if __name__ == "__main__":
    main()
