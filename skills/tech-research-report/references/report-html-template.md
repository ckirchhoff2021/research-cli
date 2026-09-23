# HTML 技术报告 CSS 设计系统（暗色主题）

经 OPD/OPSD 报告验证的已知良好样式。写 `报告名.html` 时复制修改。

## 根变量

```css
:root {
  --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3;
  --muted:#8b949e; --accent:#58a6ff; --green:#3fb950; --purple:#bc8cff;
  --amber:#d29922; --rose:#f85149; --cyan:#39c5cf;
}
body { background:var(--bg); color:var(--text);
  font-family:-apple-system,"PingFang SC","Noto Sans SC",sans-serif; line-height:1.85; }
.container { max-width:960px; margin:0 auto; padding:40px 24px 80px; }
```

## 关键组件样式

```css
/* 标题 */
h1 { font-size:28px; margin-bottom:12px; }
h2 { font-size:22px; margin:48px 0 16px; padding-bottom:8px; border-bottom:1px solid var(--border); }
h3 { font-size:17px; margin:28px 0 12px; color:var(--accent); }

/* 徽章（主题标签） */
.badge { display:inline-block; padding:1px 10px; border-radius:12px; font-size:12px;
  border:1px solid var(--border); color:var(--accent); margin-right:8px; }

/* 行内代码与代码块 */
code { background:#1f2937; padding:1px 6px; border-radius:4px;
  font-family:"JetBrains Mono",Menlo,monospace; font-size:13px; color:var(--cyan); }
pre { background:#0a0e14; border:1px solid var(--border); border-radius:8px;
  padding:16px; overflow-x:auto; margin:14px 0; font-size:13px; line-height:1.6; }
pre code { background:none; padding:0; color:#d1d9e0; }

/* 公式块（不依赖 LaTeX）：紫左边框等宽字体 */
.formula { background:#0a0e14; border-left:3px solid var(--purple); padding:12px 18px;
  margin:14px 0; border-radius:0 8px 8px 0; font-family:Menlo,monospace;
  font-size:14px; overflow-x:auto; }
/* 上下标用 <sub>/<sup>；变量名用 π<sub>θ</sub> 这类写法 */

/* 表格 */
table { border-collapse:collapse; width:100%; margin:16px 0; font-size:13.5px; }
th,td { border:1px solid var(--border); padding:8px 12px; text-align:left; vertical-align:top; }
th { background:var(--panel); color:var(--accent); white-space:nowrap; }
tr:nth-child(even) td { background:rgba(255,255,255,0.02); }

/* 引用与提示框 */
blockquote { border-left:3px solid var(--accent); padding:8px 18px; margin:16px 0;
  background:var(--panel); border-radius:0 8px 8px 0; color:var(--muted); font-size:14px; }
.callout { border:1px solid var(--border); border-radius:10px; padding:16px 20px;
  margin:18px 0; background:var(--panel); }
.callout.warn { border-color:var(--amber); }   /* 可信度声明、注意事项 */
.callout.key  { border-color:var(--green); }   /* 核心结论高亮 */
.callout .title { font-weight:600; margin-bottom:6px; font-size:14px; }
.callout.key  .title { color:var(--green); }
.callout.warn .title { color:var(--amber); }

/* 架构图嵌入：iframe 指向同目录 diagrams/*.html */
figure { margin:28px 0; }
figure iframe { width:100%; height:860px; border:1px solid var(--border);
  border-radius:12px; background:#020617; }
figcaption { text-align:center; color:var(--muted); font-size:13px; margin-top:8px; }
/* 注意：多层架构图（6-7 层）用 860px；简单图（2-3 层）可缩到 600-700px */

/* 列表与段落基线（防止浏览器默认 margin/padding 过大） */
ul, ol { padding-left:24px; }
li { margin:6px 0; font-size:15px; }
p { margin:12px 0; font-size:15px; }
strong { color:#fff; }
hr { border:none; border-top:1px solid var(--border); margin:40px 0; }
a { color:var(--accent); }

/* 页脚 */
.footer { text-align:center; color:var(--muted); font-size:12px; margin-top:60px;
  padding-top:20px; border-top:1px solid var(--border); }

/* 目录导航（页面顶部，锚点跳转） */
.toc { background:var(--panel); border:1px solid var(--border); border-radius:10px;
  padding:20px 28px; margin:24px 0 40px; }
.toc h2 { border:none; margin:0 0 12px; font-size:16px; color:var(--accent); padding:0; }
.toc ol { padding-left:20px; margin:0; }
.toc li { margin:4px 0; font-size:14px; }
.toc a { color:var(--text); text-decoration:none; }
.toc a:hover { color:var(--accent); text-decoration:underline; }

/* 强调色 */
.strong-green { color:var(--green); font-weight:600; }
.strong-rose  { color:var(--rose);  font-weight:600; }
```

## 页面结构

```
<header> 标题 + badge 行 + meta（调研来源/日期）
<nav class="toc"> 目录锚点
<h2 id="secN"> 各章…（图插在对应章节内）
<div class="footer"> 生成信息
```

注意：iframe 加载 `diagrams/` 下相对路径的独立 HTML 图，所以交付时必须保持目录结构整体移动（md/html/diagrams 一起）。
