#!/usr/bin/env python3
"""把内容目录导出为一个自包含的静态 HTML 画廊。

与 server.py 不同，本脚本不启动服务，而是把目录清单、样式和渲染逻辑全部
写入单个 HTML；文件本体通过相对路径引用，直接双击 HTML 即可离线预览。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_ROOT = REPO_ROOT / "outputs"
DEFAULT_OUTPUT = DEFAULT_ROOT / "index.html"

KINDS = [
    ("video", "视频", "🎬", ["mp4", "webm", "mov", "mkv", "avi", "m4v"]),
    ("image", "图片", "🖼️", ["jpg", "jpeg", "png", "gif", "webp", "svg", "avif", "bmp"]),
    ("audio", "音频", "🎵", ["mp3", "wav", "m4a", "flac", "ogg", "aac"]),
    ("document", "文档", "📄", ["md", "txt", "pdf", "docx"]),
    ("web", "网页", "🌐", ["html", "htm"]),
    ("code", "代码", "⌘", ["py", "js", "css", "sh", "ts", "tsx", "jsx", "sql", "yaml", "yml"]),
    ("data", "数据", "⚙️", ["json", "csv", "tsv", "xml", "toml"]),
    ("log", "日志", "📝", ["log"]),
]
EXT_TO_KIND = {ext: kind for kind, _, _, exts in KINDS for ext in exts}
SKIP_OUTPUT_NAMES = {"index.html"}


def kind_of(ext: str) -> str:
    return EXT_TO_KIND.get(ext.lower(), "other")


def is_hidden(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def collect_files(directory: Path, root: Path) -> list[dict]:
    files: list[dict] = []
    for child in sorted(directory.rglob("*"), key=lambda p: p.as_posix().lower()):
        rel = child.relative_to(root)
        if not child.is_file() or child.is_symlink() or is_hidden(rel):
            continue
        if rel.parts[0] == "_dashboard":
            continue
        if len(rel.parts) == 1 and child.name in SKIP_OUTPUT_NAMES:
            continue
        stat = child.stat()
        ext = child.suffix.lower().lstrip(".")
        files.append({
            "name": child.name,
            "path": rel.as_posix(),
            "ext": ext,
            "kind": kind_of(ext),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        })
    return files


def make_project(name: str, path: str, files: list[dict], mtime: float) -> dict:
    counts: dict[str, int] = {}
    for item in files:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    cover = next((f for f in files if f["kind"] == "image"), None)
    return {
        "name": name, "path": path, "files": sorted(files, key=lambda f: f["name"].lower()),
        "counts": counts, "size": sum(f["size"] for f in files),
        "mtime": mtime, "cover": cover["path"] if cover else None,
        "videoCover": next((f["path"] for f in files if f["kind"] == "video"), None),
    }


def file_meta(item: Path, root: Path) -> dict:
    rel = item.relative_to(root)
    stat = item.stat()
    ext = item.suffix.lower().lstrip(".")
    return {"name": item.name, "path": rel.as_posix(), "ext": ext,
            "kind": kind_of(ext), "size": stat.st_size, "mtime": stat.st_mtime}


def build_categories(root: Path) -> list[dict]:
    categories: list[dict] = []
    top_dirs = [p for p in sorted(root.iterdir(), key=lambda p: p.name.lower())
                if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")
                and p.name != "_dashboard"]
    for top in top_dirs:
        projects: list[dict] = []
        subdirs = [p for p in sorted(top.iterdir(), key=lambda p: p.name.lower())
                   if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")]
        for sub in subdirs:
            files = collect_files(sub, root)
            if files:
                projects.append(make_project(sub.name, sub.relative_to(root).as_posix(),
                                             files, sub.stat().st_mtime))
        loose_files = []
        for item in sorted(top.iterdir(), key=lambda p: p.name.lower()):
            rel = item.relative_to(root)
            if item.is_file() and not item.is_symlink() and not is_hidden(rel):
                loose_files.append(file_meta(item, root))
        if loose_files:
            projects.append(make_project("（分类根目录文件）", top.relative_to(root).as_posix(),
                                         loose_files, top.stat().st_mtime))
        cat_mtime = max([p["mtime"] for p in projects], default=top.stat().st_mtime)
        key = top.relative_to(root).as_posix()
        categories.append({"key": key, "name": top.name, "path": key,
                           "projects": projects, "mtime": cat_mtime})

    root_files = []
    for item in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        rel = item.relative_to(root)
        if item.is_file() and not item.is_symlink() and not is_hidden(rel) \
                and item.name not in SKIP_OUTPUT_NAMES:
            root_files.append(file_meta(item, root))
    if root_files:
        categories.append({
            "key": "_root", "name": "根目录散文件", "path": "",
            "projects": [make_project("（根目录文件）", "", root_files, root.stat().st_mtime)],
            "mtime": root.stat().st_mtime,
        })
    return categories


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Outputs 离线作品库</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%9C%A8%3C/text%3E%3C/svg%3E" />
<style>
:root{
  --bg:#0e1016; --panel:#161a23; --panel-2:#1d2230; --line:#262d3d;
  --text:#e8ecf4; --muted:#93a0b5; --accent:#7c9cff; --accent-2:#9d7cff;
  --shadow:0 18px 50px rgba(0,0,0,.35); --radius:18px;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;}
a{color:inherit;text-decoration:none}
button,input{font:inherit;color:inherit}
.shell{display:grid;grid-template-columns:264px 1fr;min-height:100vh}
.sidebar{background:var(--panel);border-right:1px solid var(--line);
  padding:22px 16px;display:flex;flex-direction:column;gap:18px;position:sticky;top:0;height:100vh;overflow:auto}
.brand{display:flex;gap:10px;align-items:center;padding:4px 6px}
.brand .mark{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;
  background:linear-gradient(135deg,var(--accent),var(--accent-2));font-weight:700}
.brand strong{display:block;font-size:15px}.brand small{color:var(--muted);font-size:12px}
.search{position:relative}.search span{position:absolute;left:12px;top:9px;color:var(--muted)}
.search input{width:100%;background:var(--panel-2);border:1px solid var(--line);border-radius:11px;
  padding:9px 12px 9px 34px;outline:none}
.search input:focus{border-color:var(--accent)}
.nav-title{font-size:11px;letter-spacing:.14em;color:var(--muted);text-transform:uppercase;margin:2px 6px 8px}
.nav a{display:block;padding:8px 10px;border-radius:10px;color:var(--muted);font-size:14px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav a:hover{background:var(--panel-2);color:var(--text)}
.nav a.active{background:linear-gradient(135deg,rgba(124,156,255,.22),rgba(157,124,255,.18));color:var(--text)}
.nav a .count{float:right;color:var(--muted);font-size:12px}
.side-foot{margin-top:auto;font-size:12px;color:var(--muted);padding:6px}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#58d18a;margin-right:6px}
.main{padding:26px 30px 60px;min-width:0}
.crumbs{color:var(--muted);font-size:13px;margin-bottom:18px}
.crumbs a:hover{color:var(--accent)}
h1{font-size:24px;margin:0 0 6px}h2{font-size:17px;margin:30px 0 12px}
.sub{color:var(--muted);font-size:13px;margin-bottom:22px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:8px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px}
.stat .n{font-size:24px;font-weight:700}.stat .l{color:var(--muted);font-size:12px;margin-top:2px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}
.chip{background:var(--panel-2);border:1px solid var(--line);border-radius:999px;
  padding:7px 14px;font-size:13px;color:var(--muted);cursor:pointer}
.chip:hover{color:var(--text);border-color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  overflow:hidden;cursor:pointer;transition:transform .15s,border-color .15s}
.card:hover{transform:translateY(-3px);border-color:var(--accent)}
.card .cover{aspect-ratio:3/4;background:var(--panel-2);display:grid;place-items:center;
  font-size:34px;overflow:hidden}
.card .cover img{width:100%;height:100%;object-fit:cover}
.card video{width:100%;height:100%;object-fit:cover}
.card .meta{padding:11px 13px}
.card .meta .t{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .meta .d{color:var(--muted);font-size:12px;margin-top:3px}
.wide .card .cover{aspect-ratio:16/9}
.photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px}
.photos img{width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:12px;cursor:pointer;
  border:1px solid var(--line);background:var(--panel-2)}
.photos img:hover{border-color:var(--accent)}
.videos{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.videos video{width:100%;border-radius:12px;background:#000;border:1px solid var(--line)}
.files{display:flex;flex-direction:column;gap:8px}
.file{display:flex;align-items:center;gap:10px;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;padding:10px 14px;font-size:13px}
.file:hover{border-color:var(--accent)}
.file .ic{font-size:17px}.file .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file .sz{color:var(--muted);font-size:12px}
.hero{background:linear-gradient(135deg,rgba(124,156,255,.16),rgba(157,124,255,.1));
  border:1px solid var(--line);border-radius:22px;padding:28px 30px;margin-bottom:22px}
.hero h1{font-size:28px}.hero p{color:var(--muted);margin:6px 0 0}
.cat-cover{aspect-ratio:16/9}
.empty{color:var(--muted);padding:40px;text-align:center}
.lightbox{position:fixed;inset:0;background:rgba(5,7,12,.92);display:flex;align-items:center;
  justify-content:center;z-index:50}
.lightbox img{max-width:92vw;max-height:88vh;border-radius:8px}
.lb-btn{position:absolute;background:rgba(255,255,255,.08);border:none;color:#fff;width:46px;height:46px;
  border-radius:50%;font-size:24px;cursor:pointer}
.lb-btn:hover{background:rgba(255,255,255,.2)}
.lb-close{top:22px;right:24px}.lb-prev{left:24px;top:50%}.lb-next{right:24px;top:50%}
.lb-cap{position:absolute;bottom:20px;left:50%;transform:translateX(-50%);color:var(--muted);font-size:13px}
@media(max-width:860px){
  .shell{grid-template-columns:1fr}
  .sidebar{position:static;height:auto}
  .main{padding:18px}
}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <a class="brand" href="#/">
      <span class="mark">✦</span>
      <span><strong>Outputs</strong><small>离线作品库</small></span>
    </a>
    <div class="search"><span>⌕</span><input id="q" type="search" placeholder="搜索项目或文件…" autocomplete="off" /></div>
    <div class="nav">
      <div class="nav-title">内容分类</div>
      <div id="catNav"></div>
    </div>
    <div class="side-foot"><span class="dot"></span><span id="status"></span></div>
  </aside>
  <main class="main" id="main"></main>
</div>
<div class="lightbox" id="lightbox" hidden>
  <button class="lb-btn lb-close" id="lbClose">×</button>
  <button class="lb-btn lb-prev" id="lbPrev">‹</button>
  <img id="lbImg" alt="" />
  <button class="lb-btn lb-next" id="lbNext">›</button>
  <div class="lb-cap" id="lbCap"></div>
</div>
<script>
const DATA = __DATA__;
const KINDS = [
  ["video","视频","🎬"],["image","图片","🖼️"],["audio","音频","🎵"],
  ["document","文档","📄"],["web","网页","🌐"],["code","代码","⌘"],
  ["data","数据","⚙️"],["log","日志","📝"],["other","其他","📦"],
];
const kindMeta = k => KINDS.find(x => x[0] === k) || KINDS[KINDS.length - 1];
const allProjects = DATA.categories.flatMap(c => c.projects.map(p => ({...p, cat:c})));
const allFiles = allProjects.flatMap(p => p.files.map(f => ({...f, project:p})));
const fileUrl = p => encodeURI(p);
const fmtSize = n => {
  if(n < 1024) return n + " B";
  if(n < 1024*1024) return (n/1024).toFixed(1) + " KB";
  if(n < 1024*1024*1024) return (n/1024/1024).toFixed(1) + " MB";
  return (n/1024/1024/1024).toFixed(2) + " GB";
};
const el = (tag, cls, txt) => {
  const node = document.createElement(tag);
  if(cls) node.className = cls;
  if(txt != null) node.textContent = txt;
  return node;
};

function renderNav(activeCat){
  const nav = document.getElementById("catNav");
  nav.innerHTML = "";
  const home = el("a", location.hash === "#/" ? "active" : null);
  home.href = "#/";
  home.textContent = "🏠 首页  ";
  home.appendChild(el("span","count",String(allProjects.length)));
  nav.appendChild(home);
  DATA.categories.forEach(c => {
    const a = el("a", activeCat === c.key ? "active" : null);
    a.href = "#/category/" + encodeURIComponent(c.key);
    const count = c.projects.reduce((n,p) => n + p.files.length, 0);
    a.textContent = c.name + "  ";
    a.appendChild(el("span","count",String(count)));
    a.title = c.name;
    nav.appendChild(a);
  });
  document.getElementById("status").textContent =
    allFiles.length + " 个文件 · " + DATA.generatedAt;
}

function crumbs(parts){
  const box = el("div","crumbs");
  box.appendChild(Object.assign(el("a",null,"首页"),{href:"#/"}));
  parts.forEach(p => {
    box.appendChild(el("span",null," / "));
    if(p.href){
      const a = el("a",null,p.label); a.href = p.href; box.appendChild(a);
    } else {
      box.appendChild(el("span",null,p.label));
    }
  });
  return box;
}

function projectCard(p){
  const card = el("div","card");
  const cover = el("div","cover");
  if(p.cover){
    cover.appendChild(Object.assign(el("img"),{src:fileUrl(p.cover),loading:"lazy",alt:p.name}));
  } else if(p.videoCover){
    const v = el("video");
    v.src = fileUrl(p.videoCover); v.preload = "metadata"; v.muted = true;
    cover.appendChild(v);
  } else {
    cover.textContent = kindMeta(Object.keys(p.counts)[0] || "other")[2];
  }
  card.appendChild(cover);
  const meta = el("div","meta");
  meta.appendChild(el("div","t",p.name));
  const desc = Object.entries(p.counts).map(([k,n]) => kindMeta(k)[2] + n).join("  ");
  meta.appendChild(el("div","d",desc + " · " + fmtSize(p.size)));
  card.appendChild(meta);
  card.onclick = () => location.hash = "#/project/" + encodeURIComponent(p.path);
  return card;
}

function renderHome(){
  renderNav(null);
  const main = document.getElementById("main");
  main.innerHTML = "";
  const hero = el("div","hero");
  hero.appendChild(el("h1",null,"Outputs 离线作品库"));
  hero.appendChild(el("p",null,"共 " + DATA.categories.length + " 个分类 · " +
    allProjects.length + " 个项目 · " + allFiles.length + " 个文件 · 总大小 " +
    fmtSize(allFiles.reduce((n,f) => n + f.size, 0))));
  main.appendChild(hero);

  const stats = el("div","stats");
  KINDS.slice(0,7).forEach(([k,label,icon]) => {
    const n = allFiles.filter(f => f.kind === k).length;
    if(!n) return;
    const s = el("div","stat");
    s.appendChild(el("div","n",icon + " " + n));
    s.appendChild(el("div","l",label));
    s.style.cursor = "pointer";
    s.onclick = () => location.hash = "#/kind/" + k;
    stats.appendChild(s);
  });
  main.appendChild(stats);

  const chips = el("div","chips");
  KINDS.forEach(([k,label]) => {
    const c = el("button","chip",label);
    c.onclick = () => location.hash = "#/kind/" + k;
    chips.appendChild(c);
  });
  main.appendChild(chips);

  main.appendChild(el("h2",null,"内容分类"));
  const grid = el("div","grid wide");
  DATA.categories.forEach(c => {
    const card = el("div","card");
    const cover = el("div","cover cat-cover");
    const cp = c.projects.find(p => p.cover) || c.projects[0];
    if(cp && cp.cover){
      cover.appendChild(Object.assign(el("img"),{src:fileUrl(cp.cover),loading:"lazy",alt:c.name}));
    } else {
      cover.textContent = "📁";
    }
    card.appendChild(cover);
    const meta = el("div","meta");
    meta.appendChild(el("div","t",c.name));
    const count = c.projects.reduce((n,p) => n + p.files.length, 0);
    meta.appendChild(el("div","d",c.projects.length + " 项目 · " + count + " 文件"));
    card.appendChild(meta);
    card.onclick = () => location.hash = "#/category/" + encodeURIComponent(c.key);
    grid.appendChild(card);
  });
  main.appendChild(grid);

  const recent = allProjects.slice().sort((a,b) => b.mtime - a.mtime).slice(0,8);
  main.appendChild(el("h2",null,"最近更新"));
  const rg = el("div","grid");
  recent.forEach(p => rg.appendChild(projectCard(p)));
  main.appendChild(rg);
}

function renderCategory(key){
  const cat = DATA.categories.find(c => c.key === key);
  renderNav(key);
  const main = document.getElementById("main");
  main.innerHTML = "";
  if(!cat){ main.appendChild(el("div","empty","分类不存在")); return; }
  main.appendChild(crumbs([{label:cat.name}]));
  main.appendChild(el("h1",null,cat.name));
  const count = cat.projects.reduce((n,p) => n + p.files.length, 0);
  main.appendChild(el("div","sub",cat.projects.length + " 个项目 · " + count + " 个文件"));
  const grid = el("div","grid");
  cat.projects.forEach(p => grid.appendChild(projectCard(p)));
  main.appendChild(grid);
}

let lightboxList = [], lightboxIndex = 0;
function openLightbox(list, i){
  lightboxList = list; lightboxIndex = i;
  document.getElementById("lightbox").hidden = false;
  updateLightbox();
}
function updateLightbox(){
  const f = lightboxList[lightboxIndex];
  document.getElementById("lbImg").src = fileUrl(f.path);
  document.getElementById("lbCap").textContent =
    (lightboxIndex + 1) + "/" + lightboxList.length + " · " + f.name;
}
function moveLightbox(d){
  lightboxIndex = (lightboxIndex + d + lightboxList.length) % lightboxList.length;
  updateLightbox();
}
document.getElementById("lbClose").onclick = () => document.getElementById("lightbox").hidden = true;
document.getElementById("lbPrev").onclick = () => moveLightbox(-1);
document.getElementById("lbNext").onclick = () => moveLightbox(1);
document.addEventListener("keydown", e => {
  if(document.getElementById("lightbox").hidden) return;
  if(e.key === "Escape") document.getElementById("lightbox").hidden = true;
  if(e.key === "ArrowLeft") moveLightbox(-1);
  if(e.key === "ArrowRight") moveLightbox(1);
});

function renderProject(path){
  const p = allProjects.find(x => x.path === path);
  renderNav(p ? p.cat.key : null);
  const main = document.getElementById("main");
  main.innerHTML = "";
  if(!p){ main.appendChild(el("div","empty","项目不存在")); return; }
  main.appendChild(crumbs([
    {label:p.cat.name, href:"#/category/" + encodeURIComponent(p.cat.key)},
    {label:p.name},
  ]));
  main.appendChild(el("h1",null,p.name));
  main.appendChild(el("div","sub",
    Object.entries(p.counts).map(([k,n]) => kindMeta(k)[2] + n).join("  ") +
    " · 共 " + p.files.length + " 个文件 · " + fmtSize(p.size)));

  const images = p.files.filter(f => f.kind === "image");
  const videos = p.files.filter(f => f.kind === "video");
  const audios = p.files.filter(f => f.kind === "audio");
  const others = p.files.filter(f => !["image","video","audio"].includes(f.kind));

  if(videos.length){
    main.appendChild(el("h2",null,"🎬 视频 (" + videos.length + ")"));
    const box = el("div","videos");
    videos.forEach(f => {
      const v = el("video");
      v.controls = true; v.preload = "metadata"; v.src = fileUrl(f.path);
      box.appendChild(v);
    });
    main.appendChild(box);
  }
  if(images.length){
    main.appendChild(el("h2",null,"🖼️ 图片 (" + images.length + ")"));
    const box = el("div","photos");
    images.forEach((f,i) => {
      const img = Object.assign(el("img"),{src:fileUrl(f.path),loading:"lazy",alt:f.name});
      img.onclick = () => openLightbox(images, i);
      box.appendChild(img);
    });
    main.appendChild(box);
  }
  if(audios.length){
    main.appendChild(el("h2",null,"🎵 音频 (" + audios.length + ")"));
    audios.forEach(f => {
      const a = el("audio");
      a.controls = true; a.src = fileUrl(f.path);
      a.style.width = "100%";
      main.appendChild(a);
    });
  }
  if(others.length){
    main.appendChild(el("h2",null,"📄 其他文件 (" + others.length + ")"));
    const box = el("div","files");
    others.forEach(f => {
      const a = el("a","file");
      a.href = fileUrl(f.path); a.target = "_blank";
      a.appendChild(el("span","ic",kindMeta(f.kind)[2]));
      a.appendChild(el("span","nm",f.name));
      a.appendChild(el("span","sz",fmtSize(f.size)));
      box.appendChild(a);
    });
    main.appendChild(box);
  }
}

function renderKind(kind){
  renderNav(null);
  const main = document.getElementById("main");
  main.innerHTML = "";
  const meta = kindMeta(kind);
  main.appendChild(crumbs([{label:meta[1]}]));
  const files = allFiles.filter(f => f.kind === kind);
  main.appendChild(el("h1",null,meta[2] + " " + meta[1]));
  main.appendChild(el("div","sub",files.length + " 个文件"));
  if(kind === "image"){
    const box = el("div","photos");
    files.forEach((f,i) => {
      const img = Object.assign(el("img"),{src:fileUrl(f.path),loading:"lazy",alt:f.name});
      img.onclick = () => openLightbox(files, i);
      box.appendChild(img);
    });
    main.appendChild(box);
  } else if(kind === "video"){
    const box = el("div","videos");
    files.forEach(f => {
      const v = el("video");
      v.controls = true; v.preload = "metadata"; v.src = fileUrl(f.path);
      box.appendChild(v);
    });
    main.appendChild(box);
  } else {
    const box = el("div","files");
    files.forEach(f => {
      const a = el("a","file");
      a.href = fileUrl(f.path); a.target = "_blank";
      a.appendChild(el("span","ic",meta[2]));
      a.appendChild(el("span","nm",f.path));
      a.appendChild(el("span","sz",fmtSize(f.size)));
      box.appendChild(a);
    });
    main.appendChild(box);
  }
}

function renderSearch(q){
  renderNav(null);
  const main = document.getElementById("main");
  main.innerHTML = "";
  const term = q.toLowerCase();
  main.appendChild(crumbs([{label:"搜索：" + q}]));
  const projects = allProjects.filter(p =>
    p.name.toLowerCase().includes(term) || p.path.toLowerCase().includes(term));
  const files = allFiles.filter(f =>
    f.name.toLowerCase().includes(term) || f.path.toLowerCase().includes(term));
  main.appendChild(el("h1",null,"搜索 “" + q + "”"));
  main.appendChild(el("div","sub",projects.length + " 个项目 · " + files.length + " 个文件"));
  if(projects.length){
    main.appendChild(el("h2",null,"项目"));
    const g = el("div","grid");
    projects.forEach(p => g.appendChild(projectCard(p)));
    main.appendChild(g);
  }
  if(files.length){
    main.appendChild(el("h2",null,"文件"));
    const box = el("div","files");
    files.forEach(f => {
      const a = el("a","file");
      a.href = fileUrl(f.path); a.target = "_blank";
      a.appendChild(el("span","ic",kindMeta(f.kind)[2]));
      a.appendChild(el("span","nm",f.path + " （" + f.project.name + "）"));
      a.appendChild(el("span","sz",fmtSize(f.size)));
      box.appendChild(a);
    });
    main.appendChild(box);
  }
  if(!projects.length && !files.length)
    main.appendChild(el("div","empty","没有匹配的内容"));
}

function route(){
  const h = location.hash || "#/";
  let m = h.match(/^#\/category\/(.+)$/);
  if(m){ renderCategory(decodeURIComponent(m[1])); window.scrollTo(0,0); return; }
  m = h.match(/^#\/project\/(.+)$/);
  if(m){ renderProject(decodeURIComponent(m[1])); window.scrollTo(0,0); return; }
  m = h.match(/^#\/kind\/(.+)$/);
  if(m){ renderKind(decodeURIComponent(m[1])); window.scrollTo(0,0); return; }
  m = h.match(/^#\/search\/(.+)$/);
  if(m){ renderSearch(decodeURIComponent(m[1])); window.scrollTo(0,0); return; }
  renderHome();
  window.scrollTo(0,0);
}
document.getElementById("q").addEventListener("input", e => {
  const v = e.target.value.trim();
  location.hash = v ? "#/search/" + encodeURIComponent(v) : "#/";
});
window.addEventListener("hashchange", route);
route();
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出自包含静态 HTML 画廊")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="内容目录，默认 outputs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 HTML 路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"root not found: {root}")
    categories = build_categories(root)
    total_files = sum(
        sum(p["counts"].values()) for c in categories for p in c["projects"]
    )
    data = {"root": str(root), "generatedAt": time.strftime("%Y-%m-%d %H:%M"),
            "categories": categories}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html_text = HTML_TEMPLATE.replace("__DATA__", payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    print(f"exported {total_files} files -> {args.output.resolve()} "
          f"({args.output.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
