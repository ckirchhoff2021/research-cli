(() => {
  "use strict";

  const KINDS = [
    { key: "video", label: "视频", icon: "🎬", exts: ["mp4", "webm", "mov", "mkv", "avi", "m4v"] },
    { key: "image", label: "图片", icon: "🖼️", exts: ["jpg", "jpeg", "png", "gif", "webp", "svg", "avif", "bmp"] },
    { key: "audio", label: "音频", icon: "🎵", exts: ["mp3", "wav", "m4a", "flac", "ogg", "aac"] },
    { key: "document", label: "文档", icon: "📄", exts: ["md", "txt", "pdf", "docx"] },
    { key: "web", label: "网页", icon: "🌐", exts: ["html", "htm"] },
    { key: "code", label: "代码", icon: "⌘", exts: ["py", "js", "css", "sh", "ts", "tsx", "jsx", "sql", "yaml", "yml"] },
    { key: "data", label: "数据", icon: "⚙️", exts: ["json", "csv", "tsv", "xml", "toml"] },
    { key: "log", label: "日志", icon: "📝", exts: ["log"] },
  ];

  const TAGS = [
    {
      key: "video", label: "视频创作", icon: "🎬", desc: "剧情短片、分镜成片与视频生成实验",
      score: (p, key) => (p.counts.video || 0) * 8 + (key.test(p.name) ? 120 : 0) + (p.counts.audio || 0) * 2 + ((p.counts.video || 0) >= 1 ? 25 : 0),
      keywords: /视频|短片|剧情|video|drama|movie|film|wuxia|travel|scholar|business|reunion|cg|变装|江湖|书生|都市精英|ghibli/,
    },
    {
      key: "picturebook", label: "绘本图文", icon: "📚", desc: "带插图的绘本、章节故事与图文作品",
      score: (p, key) => (key.test(p.name) ? 110 : 0) + ((p.counts.image || 0) >= 6 && (p.counts.document || 0) + (p.counts.web || 0) >= 1 ? 45 : 0),
      keywords: /绘本|picture.?book|fanren|daming|daodejing|three.?dragons|resilience|心灯|海瑞|纸船|道德经|龙族|故事/,
    },
    {
      key: "report", label: "报告教程", icon: "📊", desc: "技术调研、实现报告、方案文档与使用教程",
      score: (p, key) => (key.test(p.name) ? 110 : 0) + (p.counts.document || 0) * 7 + (p.counts.image || 0) * 0.4,
      keywords: /report|报告|调研|教程|guide|memory|rsi|anthropomorphic|emotion|opd|claude|feishu|codex|analysis|analysis|方案|tutorial/i,
    },
    {
      key: "gallery", label: "图片风格", icon: "🎨", desc: "风格迁移、人像图库、海报与视觉实验",
      score: (p, key) => (key.test(p.name) ? 95 : 0) + (p.counts.image || 0) * 1.3 + ((p.counts.image || 0) >= 10 ? 30 : 0),
      keywords: /gallery|风格|style|portrait|人像|海报|poster|images?|pictures?|img-|ghibli-img|画册|素描|照片/,
    },
    {
      key: "webapp", label: "网页应用", icon: "🌐", desc: "可交互的 HTML 页面、工具与小游戏",
      score: (p, key) => (key.test(p.name) ? 95 : 0) + (p.counts.web || 0) * 10 + (p.counts.code || 0) * 5 + (p.mainWeb && ((p.counts.code || 0) > 0 || key.test(p.name)) ? 45 : 0),
      keywords: /tank|api.?tester|llm-api|md2html|web.?app|game|网页|demo|gallery\.html|index\.html/i,
    },
    {
      key: "audio", label: "音频朗诵", icon: "🎧", desc: "诗词朗诵、配音与音频内容",
      score: (p, key) => (p.counts.audio || 0) * 12 + (key.test(p.name) ? 80 : 0),
      keywords: /audio|朗诵|朗读|配音|诗词|诗歌|xu$|mp3/,
    },
    {
      key: "novel", label: "小说文本", icon: "✒️", desc: "小说章节、大纲与散文故事",
      score: (p, key) => (key.test(p.name) ? 110 : 0) + (p.counts.document || 0) * 4,
      keywords: /novel|小说|prose|大纲|光暗之争|sunwukong|神龙故事/,
    },
    {
      key: "data", label: "实验数据", icon: "🧪", desc: "接口探测、爬取结果、日志与 JSON 数据",
      score: (p, key) => (key.test(p.name) ? 105 : 0) + ((p.counts.data || 0) + (p.counts.log || 0)) * 6,
      keywords: /probe|crawler|crawl|tokenplan|semantic|trace|loop.?engineering|实验|test_|数据/,
    },
    {
      key: "code", label: "脚本代码", icon: "🐍", desc: "生成脚本、拼接工具与自动化处理代码",
      score: (p, key) => (p.counts.code || 0) * 10 + (key.test(p.name) ? 45 : 0) + (!(p.counts.video || p.counts.image) && (p.counts.code || 0) >= 2 ? 35 : 0),
      keywords: /script|工具|tool|concat|generate|probe|py$/,
    },
  ];

  const TAG_OTHER = { key: "other", label: "综合其他", icon: "✨", desc: "混合内容与待整理项目" };
  const TEXT_EXTS = new Set(["md", "txt", "py", "js", "css", "sh", "ts", "tsx", "jsx", "sql", "yaml", "yml", "json", "csv", "tsv", "xml", "toml", "log", "svg"]);

  const CATEGORIES = [
    { key: "01", label: "视频创作", icon: "🎬", desc: "剧情短片、分镜成片与视频生成实验", accent: "#7c8cff" },
    { key: "02", label: "海报图像", icon: "🎨", desc: "海报、风格迁移图片与原始参考素材", accent: "#ff8fa3" },
    { key: "03", label: "绘本小说", icon: "📚", desc: "图文绘本、网文衍生与文学配音", accent: "#ffd166" },
    { key: "04", label: "技术报告", icon: "📊", desc: "技术调研、方案设计与实现报告", accent: "#6ee7b7" },
    { key: "05", label: "数据实验", icon: "🧪", desc: "时序预测实验、语义检索与追踪数据", accent: "#5ad1e8" },
    { key: "06", label: "工具教程", icon: "🛠️", desc: "工具型网站、Demo 与使用教程", accent: "#c792ea" },
  ];
  const CATEGORY_RE = /^(\d{2})_.+$/;

  function categoryMeta(key) {
    return CATEGORIES.find((category) => category.key === key) || null;
  }

  const state = {
    root: null,
    files: [],
    projects: [],
    categories: [],
    fileByPath: new Map(),
    projectByPath: new Map(),
    categoryByPath: new Map(),
    nodeByPath: new Map(),
    query: "",
    signature: "",
    limits: {},
    metas: new Map(),
  };

  const els = {};

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    Object.assign(els, {
      content: document.getElementById("content"),
      tagNav: document.getElementById("categoryNav"),
      projectNav: document.getElementById("projectNav"),
      search: document.getElementById("searchInput"),
      refresh: document.getElementById("refreshBtn"),
      scanStatus: document.getElementById("scanStatus"),
      breadcrumbs: document.getElementById("breadcrumbs"),
      sidebar: document.getElementById("sidebar"),
      menu: document.getElementById("menuBtn"),
      autoRefresh: document.getElementById("autoRefresh"),
      lightbox: document.getElementById("lightbox"),
      lightboxImage: document.getElementById("lightboxImage"),
      lightboxClose: document.getElementById("lightboxClose"),
      lightboxPrev: document.getElementById("lightboxPrev"),
      lightboxNext: document.getElementById("lightboxNext"),
      toast: document.getElementById("toast"),
    });

    els.refresh.addEventListener("click", () => loadTree(true));
    els.search.addEventListener("input", () => {
      state.query = els.search.value.trim().toLowerCase();
      if (route().type !== "home") location.hash = "#/";
      else render();
    });
    window.addEventListener("hashchange", render);
    window.setInterval(pollTree, 20000);
    document.addEventListener("click", handleGlobalClick);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !els.lightbox.hidden) closeLightbox();
      if (!els.lightbox.hidden && event.key === "ArrowLeft") moveLightbox(-1);
      if (!els.lightbox.hidden && event.key === "ArrowRight") moveLightbox(1);
    });
    els.lightboxClose.addEventListener("click", closeLightbox);
    els.lightboxPrev.addEventListener("click", () => moveLightbox(-1));
    els.lightboxNext.addEventListener("click", () => moveLightbox(1));
    els.menu.addEventListener("click", () => els.sidebar.classList.toggle("open"));
    els.search.title = "按 / 键可快速聚焦搜索框";
    buildBackToTop();
    buildSidebarBackdrop();
    document.addEventListener("keydown", handleShortcuts);
    loadTree(false);
  }

  async function loadTree(manual) {
    try {
      els.scanStatus.textContent = "正在扫描…";
      const root = await fetchJson("/api/tree");
      const signature = JSON.stringify({ count: countTree(root), mtime: root.mtime, size: root.size });
      const changed = signature !== state.signature;
      state.root = root;
      state.signature = signature;
      indexTree(root);
      render();
      if (manual && changed) toast("已同步 outputs 目录");
      els.scanStatus.textContent = `${state.projects.length} 个项目 · 自动扫描`;
    } catch (error) {
      els.scanStatus.textContent = "扫描失败";
      els.content.innerHTML = emptyBlock(`无法读取目录：${escapeHtml(error.message)}`);
    }
  }

  async function pollTree() {
    if (!els.autoRefresh.checked) return;
    try {
      const root = await fetchJson("/api/tree");
      const signature = JSON.stringify({ count: countTree(root), mtime: root.mtime, size: root.size });
      if (state.root && signature !== state.signature) {
        state.root = root;
        state.signature = signature;
        indexTree(root);
        render();
        toast("检测到新内容，已自动同步");
      }
    } catch {
      // polling is best effort
    }
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, { cache: "no-store", ...options });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function countTree(node) {
    if (node.type === "file") return 1;
    return (node.children || []).reduce((sum, child) => sum + countTree(child), 0);
  }

  function indexTree(root) {
    state.nodeByPath = new Map();
    const register = (node) => {
      state.nodeByPath.set(node.path || "", node);
      if (node.type === "directory") (node.children || []).forEach(register);
    };
    register(root);
    state.nodeByPath.set("__root__", root);

    const files = collectFiles(root).sort(comparePaths);
    state.files = files;
    state.fileByPath = new Map(files.map((file) => [file.path, file]));

    const rootFiles = (root.children || []).filter(
      (node) => node.type === "file" && node.name.toLowerCase() !== "readme.md"
    );
    const projects = [];
    const categories = [];
    if (rootFiles.length) {
      projects.push(makeProject({
        type: "directory", name: "根目录散文件", path: "__root__", synthetic: true,
        children: rootFiles,
        mtime: Math.max(...rootFiles.map((file) => file.mtime)),
        size: rootFiles.reduce((sum, file) => sum + file.size, 0),
      }, ""));
    }
    for (const node of (root.children || [])) {
      if (node.type !== "directory") continue;
      const match = CATEGORY_RE.exec(node.name);
      if (!match) {
        projects.push(makeProject(node, ""));
        continue;
      }
      const category = { key: match[1], node, path: node.path, projects: [] };
      const looseFiles = [];
      for (const child of (node.children || [])) {
        if (child.type === "directory") {
          const project = makeProject(child, category.key);
          projects.push(project);
          category.projects.push(project);
        } else {
          looseFiles.push(child);
        }
      }
      if (looseFiles.length) {
        const miscProject = makeProject({
          type: "directory", name: "__misc__", path: `${node.path}/__misc__`,
          synthetic: true, children: looseFiles,
          mtime: Math.max(...looseFiles.map((file) => file.mtime)),
          size: looseFiles.reduce((sum, file) => sum + file.size, 0),
        }, category.key);
        projects.push(miscProject);
        category.projects.push(miscProject);
      }
      categories.push(category);
    }
    projects.sort(compareProjects);
    state.projects = projects;
    state.categories = categories;
    state.projectByPath = new Map(projects.map((project) => [project.path, project]));
    state.categoryByPath = new Map(categories.map((category) => [category.path, category]));
  }

  function compareProjects(a, b) {
    const categoryOrder = (key) => (key ? key : "zz");
    const left = categoryOrder(a.categoryKey);
    const right = categoryOrder(b.categoryKey);
    if (left !== right) return left.localeCompare(right);
    return b.quality - a.quality || b.mtime - a.mtime;
  }

  function makeProject(node, categoryKey) {
    const files = collectFiles(node).sort(comparePaths);
    const counts = {};
    for (const file of files) {
      const kind = kindOf(file);
      counts[kind] = (counts[kind] || 0) + 1;
    }
    const byKind = (kind) => files.filter((file) => kindOf(file) === kind);
    const images = byKind("image");
    const videos = byKind("video");
    const audios = byKind("audio");
    const webs = byKind("web");
    const docs = byKind("document");

    const project = {
      node,
      name: node.name === "__misc__" ? "分类散文件" : humanizeName(node.name),
      path: node.path,
      synthetic: Boolean(node.synthetic),
      categoryKey: categoryKey || "",
      files,
      counts,
      images,
      videos,
      audios,
      webs,
      docs,
      code: byKind("code"),
      data: byKind("data"),
      logs: byKind("log"),
      cover: chooseCover(images),
      thumbnails: [],
      mainVideo: chooseMainVideo(videos),
      mainAudio: audios.sort((a, b) => b.size - a.size)[0] || null,
      mainWeb: chooseMainWeb(webs, node.name),
      readme: chooseReadme(docs),
      size: node.size || files.reduce((sum, file) => sum + file.size, 0),
      mtime: node.mtime || 0,
      tag: "other",
      tags: ["other"],
      quality: 0,
    };
    project.thumbnails = chooseThumbnails(images, project.cover);
    assignTag(project);
    project.quality = qualityScore(project);
    return project;
  }

  function assignTag(project) {
    const tagScope = { ...project, name: `${project.name} ${project.path}`.toLowerCase() };
    const scored = TAGS.map((tag) => {
      return { key: tag.key, score: tag.score(tagScope, tag.keywords) };
    }).sort((a, b) => b.score - a.score);
    const primary = scored[0]?.score >= 20 ? scored[0].key : "other";
    const secondary = scored.filter((item) => item.score >= 35 && item.key !== primary).slice(0, 3).map((item) => item.key);
    project.tag = primary;
    project.tags = [primary, ...secondary];
  }

  function qualityScore(project) {
    let score = Math.min(42, project.files.length);
    if (project.cover) score += 46;
    if (project.thumbnails.length >= 4) score += 14;
    if (project.mainVideo) score += 72;
    if (project.mainVideo && /final|完整|成片|版|main/.test(project.mainVideo.name)) score += 28;
    if (project.videos.length >= 3) score += 12;
    if (project.readme) score += 18;
    if (project.mainWeb) score += 22;
    if (project.docs.length >= 2) score += 8;
    if (project.code.length) score += 6;
    if (project.images.length >= 20) score += 16;
    if (project.audios.length) score += 8;
    const ageDays = (Date.now() / 1000 - project.mtime) / 86400;
    if (ageDays <= 2) score += 26;
    else if (ageDays <= 7) score += 18;
    else if (ageDays <= 30) score += 10;
    return score;
  }

  function collectFiles(node) {
    if (node.type === "file") return [node];
    return (node.children || []).flatMap(collectFiles);
  }

  function comparePaths(a, b) {
    return a.path.localeCompare(b.path, "zh-Hans-CN", { numeric: true, sensitivity: "base" });
  }

  function kindOf(file) {
    const ext = (file.ext || "").toLowerCase();
    const kind = KINDS.find((item) => item.exts.includes(ext));
    return kind ? kind.key : "other";
  }

  function kindMeta(key) {
    return KINDS.find((kind) => kind.key === key) || { key, label: "其他", icon: "📦" };
  }

  function tagMeta(key) {
    return TAGS.find((tag) => tag.key === key) || TAG_OTHER;
  }

  function chooseCover(images) {
    return images.length ? [...images].sort((a, b) => coverScore(b) - coverScore(a))[0] : null;
  }

  function chooseThumbnails(images, cover) {
    return [...images]
      .sort((a, b) => coverScore(b) - coverScore(a))
      .filter((file) => !cover || file.path !== cover.path)
      .slice(0, 5);
  }

  function coverScore(file) {
    const name = file.name.toLowerCase();
    const depth = file.path.split("/").length - 1;
    let score = depth === 0 ? 100 : Math.max(5, 78 - depth * 16);
    if (/(cover|poster|ref|封面|参考|^00_|^01_|chapter1)/.test(name)) score += 70;
    if (/(final|selected|main|完整)/.test(name)) score += 34;
    if (/(thumb|icon|avatar|small|favicon)/.test(name)) score -= 90;
    return score;
  }

  function chooseMainVideo(videos) {
    return videos.length ? [...videos].sort((a, b) => mainVideoScore(b) - mainVideoScore(a))[0] : null;
  }

  function mainVideoScore(file) {
    const name = file.name.toLowerCase();
    const depth = file.path.split("/").length - 1;
    let score = depth === 0 ? 100 : 10;
    if (/(final|完整|成片|main|concat|版)/.test(name)) score += 130;
    if (/segments?|parts?|片段/.test(file.path)) score -= 120;
    score += Math.min(50, Math.log10(file.size + 1) * 8);
    return score;
  }

  function chooseMainWeb(files, projectName) {
    if (!files.length) return null;
    return [...files].sort((a, b) => mainNamedScore(b, projectName) - mainNamedScore(a, projectName))[0];
  }

  function chooseReadme(files) {
    const markdown = files.filter((file) => file.ext === "md");
    if (!markdown.length) return files[0] || null;
    return [...markdown].sort((a, b) => readmeScore(b) - readmeScore(a))[0];
  }

  function readmeScore(file) {
    const name = file.name.toLowerCase();
    const depth = file.path.split("/").length - 1;
    let score = 30 - depth * 5;
    if (name === "readme.md") score += 120;
    if (/报告|教程|guide|report|design|readme/i.test(file.name)) score += 60;
    return score + (file.ext === "md" ? 20 : 0);
  }

  function mainNamedScore(file, projectName) {
    const name = file.name.toLowerCase();
    const depth = file.path.split("/").length - 1;
    let score = depth === 0 ? 60 : 10;
    if (name === "index.html") score += 90;
    if (projectName && name.includes(projectName.toLowerCase())) score += 80;
    if (/report|报告|main|final|完整/.test(name)) score += 40;
    return score;
  }

  function render() {
    if (!state.root) {
      els.content.innerHTML = `<div class="loading">正在扫描 outputs 文件夹</div>`;
      return;
    }
    renderChrome();
    const current = route();
    if (current.type === "tag") renderTag(current.key);
    else if (current.type === "category") renderCategory(current.key);
    else if (current.type === "project") renderProjectOrList(current);
    else if (current.type === "dir") renderDirOrList(current);
    else if (current.type === "file") renderFile(current.path);
    else renderHome();
    els.sidebar.classList.remove("open");
    window.scrollTo({ top: 0 });
  }

  function route() {
    let hash = location.hash || "#/";
    try { hash = decodeURIComponent(hash); } catch { /* keep raw */ }
    const known = KINDS.map((kind) => kind.key).join("|");
    let match = hash.match(new RegExp(`^#/project/(.+?)(?:/(${known}))?$`));
    if (match) return { type: "project", path: match[1], kind: match[2] || "" };
    match = hash.match(new RegExp(`^#/dir/(.+?)(?:/(${known}))?$`));
    if (match) return { type: "dir", path: match[1], kind: match[2] || "" };
    match = hash.match(/^#\/tag\/([^/]+)$/);
    if (match) return { type: "tag", key: match[1] };
    match = hash.match(/^#\/category\/([^/]+)$/);
    if (match) return { type: "category", key: match[1] };
    match = hash.match(/^#\/file\/(.+)$/);
    if (match) return { type: "file", path: match[1] };
    return { type: "home" };
  }

  function renderChrome() {
    const current = route();
    const activeCategory = current.type === "category" ? current.key
      : current.type === "home" && !state.query ? "all" : "";
    const navLinks = [`
      <a class="tag-link ${activeCategory === "all" ? "active" : ""}" href="#/">
        <span class="tag-link-icon">✦</span>
        <span class="tag-link-label">全部作品</span>
        <em>${state.projects.length}</em>
      </a>`];
    for (const category of state.categories) {
      const meta = categoryMeta(category.key);
      navLinks.push(`
        <a class="tag-link cat-nav-${category.key} ${activeCategory === category.key ? "active" : ""}"
           style="--cat-accent:${meta.accent}" href="#/category/${encodeURIComponent(category.key)}">
          <span class="tag-link-icon">${meta.icon}</span>
          <span class="tag-link-label">${meta.label}</span>
          <em>${category.projects.length}</em>
        </a>`);
    }
    els.tagNav.innerHTML = navLinks.join("");

    const activeProject = currentProjectPath();
    const legacyProjects = state.projects.filter((project) => !project.categoryKey);
    const groupsHtml = state.categories.map((category) => {
      const meta = categoryMeta(category.key);
      return `
        <div class="project-nav-group">
          <p class="project-nav-title" style="--cat-accent:${meta.accent}">${meta.icon} ${meta.label}</p>
          ${category.projects.map((project) => projectNavLink(project, activeProject)).join("")}
        </div>`;
    }).join("");
    const legacyHtml = legacyProjects.length ? `
      <div class="project-nav-group">
        <p class="project-nav-title">未分类</p>
        ${legacyProjects.map((project) => projectNavLink(project, activeProject)).join("")}
      </div>` : "";
    els.projectNav.innerHTML = groupsHtml + legacyHtml;
    revealActiveNav();
  }

  function projectNavLink(project, activeProject) {
    return `
      <a class="project-link ${activeProject === project.path ? "active" : ""}"
         href="#/project/${encodeURIComponent(project.path)}" title="${escapeAttr(project.path)}"
         ${project.categoryKey ? `style="--cat-accent:${categoryMeta(project.categoryKey).accent}"` : ""}>
        <span>${tagMeta(project.tag).icon}</span>
        <span>${escapeHtml(project.name)}</span>
      </a>`;
  }

  function buildBackToTop() {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "back-to-top";
    btn.textContent = "↑";
    btn.setAttribute("aria-label", "回到顶部");
    btn.hidden = true;
    document.body.appendChild(btn);
    btn.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    const toggle = () => { btn.hidden = window.scrollY < 480; };
    window.addEventListener("scroll", toggle, { passive: true });
    toggle();
  }

  function buildSidebarBackdrop() {
    const backdrop = document.createElement("div");
    backdrop.className = "sidebar-backdrop";
    backdrop.hidden = true;
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", () => els.sidebar.classList.remove("open"));
    const sync = () => { backdrop.hidden = !els.sidebar.classList.contains("open"); };
    new MutationObserver(sync).observe(els.sidebar, {
      attributes: true,
      attributeFilter: ["class"],
    });
    sync();
  }

  function handleShortcuts(event) {
    const tag = document.activeElement?.tagName || "";
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(tag);
    if (event.key === "/" && !typing) {
      event.preventDefault();
      els.search.focus();
      return;
    }
    if (event.key === "Escape" && document.activeElement === els.search && els.search.value) {
      els.search.value = "";
      state.query = "";
      if (route().type !== "home") location.hash = "#/";
      else render();
    }
  }

  function revealActiveNav() {
    const active = els.projectNav.querySelector(".project-link.active");
    if (!active) return;
    const navRect = els.projectNav.getBoundingClientRect();
    const linkRect = active.getBoundingClientRect();
    if (linkRect.top < navRect.top + 8 || linkRect.bottom > navRect.bottom - 8) {
      active.scrollIntoView({ block: "nearest" });
    }
  }

  function currentProjectPath() {
    const current = route();
    if (current.type === "project") return current.path;
    if (current.type === "dir") return ownerPath(current.path);
    if (current.type === "file") return ownerPath(current.path);
    return null;
  }

  function ownerPath(path) {
    if (path === "__root__") return "__root__";
    const parts = path.split("/");
    if (parts.length === 1) return state.projectByPath.has(parts[0]) ? parts[0] : "__root__";
    if (!CATEGORY_RE.test(parts[0])) return parts[0];
    if (parts.length === 2) return `${parts[0]}/__misc__`;
    return `${parts[0]}/${parts[1]}`;
  }

  function renderHome() {
    const query = state.query;
    els.breadcrumbs.innerHTML = `<a href="#/">Outputs</a><span>›</span><span>${query ? "搜索结果" : "作品总览"}</span>`;

    if (query) return renderSearch(query);

    const featured = state.projects.filter((project) => project.quality >= 95 && (project.cover || project.mainVideo || project.mainWeb)).slice(0, 5);
    const hero = featured[0];
    const totalSize = state.files.reduce((sum, file) => sum + file.size, 0);
    const stats = [
      ["项目", state.projects.length, "✦"],
      ["视频", totalKind("video"), "🎬"],
      ["图片", totalKind("image"), "🖼️"],
      ["音频", totalKind("audio"), "🎵"],
      ["文档", totalKind("document"), "📄"],
      ["占用", formatBytes(totalSize), "💾"],
    ];

    els.content.innerHTML = `
      <section class="hero">
        <p class="eyebrow">Offline Creative Library</p>
        <h1>按知识库分类整理的离线作品库</h1>
        <p>六大主题分类收纳视频、海报、绘本、报告、实验与工具作品。摘要在本地预生成并缓存，新增内容刷新即可出现，无需重新生成页面。</p>
        <div class="stat-grid">${stats.map(([label, value, icon]) => `<div class="stat-card"><strong>${icon} ${value}</strong><span>${label}</span></div>`).join("")}</div>
      </section>

      ${hero ? `
        <section class="section">
          <div class="section-head"><div><h2>优质内容</h2><p>根据完整度、封面、成片、文档与更新时间自动挑选</p></div></div>
          <div class="featured-layout">
            ${featuredHero(hero)}
            <div class="featured-side">${featured.slice(1, 5).map(featuredSmall).join("")}</div>
          </div>
        </section>` : ""}

      <section class="section">
        <div class="section-head"><div><h2>知识库分类</h2><p>点击分类后按目录缩略浏览，再点击目录进入项目</p></div></div>
        <div class="category-grid">
          ${state.categories.map(categoryCard).join("")}
        </div>
      </section>

      <section class="section">
        <div class="section-head"><div><h2>按内容类型</h2><p>跨知识库的内容类型标签</p></div></div>
        <div class="tag-grid">
          ${TAGS.map((tag) => {
            const projects = projectsByTag(tag.key);
            const names = projects.slice(0, 3).map((project) => escapeHtml(project.name)).join("、");
            return `
              <a class="tag-card tag-${tag.key}" href="#/tag/${encodeURIComponent(tag.key)}">
                <span class="tag-card-icon">${tag.icon}</span>
                <strong>${tag.label}</strong>
                <small>${tag.desc}</small>
                <em>${projects.length} 个项目</em>
                <p>${names || "等待新内容加入"}</p>
              </a>`;
          }).join("")}
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <div><h2>最近项目</h2><p>按项目浏览，不枚举散落文件</p></div>
          <a class="ghost-btn" href="#/tag/all">查看全部</a>
        </div>
        <div class="project-grid compact-grid">${[...state.projects].sort((a, b) => b.mtime - a.mtime).slice(0, 8).map(projectCard).join("")}</div>
      </section>
    `;
  }

  function featuredHero(project) {
    const background = project.cover ? `style="background-image:linear-gradient(135deg,rgba(8,11,20,.92),rgba(8,11,20,.42)),url('${rawUrl(project.cover.path)}')"` : "";
    return `
      <a class="featured-hero" ${background} href="#/project/${encodeURIComponent(project.path)}">
        <div class="featured-hero-content">
          <span class="featured-badge">${tagMeta(project.tag).icon} ${tagMeta(project.tag).label}</span>
          <h2>${escapeHtml(project.name)}</h2>
          <p>${escapeHtml(projectSummaryLine(project))}</p>
          <span class="featured-cta">进入项目 →</span>
        </div>
      </a>
    `;
  }

  function featuredSmall(project) {
    return `
      <a class="featured-small" href="#/project/${encodeURIComponent(project.path)}">
        ${project.cover ? `<img loading="lazy" src="${rawUrl(project.cover.path)}" alt="${escapeAttr(project.name)}">` : `<div class="featured-fallback">${tagMeta(project.tag).icon}</div>`}
        <div><strong>${escapeHtml(project.name)}</strong><small>${kindCountsLine(project)}</small></div>
      </a>
    `;
  }

  function categoryCard(category) {
    const meta = categoryMeta(category.key);
    const coverFiles = category.projects
      .map((project) => project.cover)
      .filter(Boolean)
      .slice(0, 4);
    const visual = coverFiles.length
      ? `<div class="cat-mosaic">${coverFiles.map((file) => `<img loading="lazy" src="${rawUrl(file.path)}" alt="">`).join("")}</div>`
      : `<div class="cat-mosaic cat-mosaic-empty"><span>${meta.icon}</span></div>`;
    return `
      <a class="cat-card cat-card-${category.key}" style="--cat-accent:${meta.accent}"
         href="#/category/${encodeURIComponent(category.key)}">
        ${visual}
        <div class="cat-card-body">
          <strong>${meta.icon} ${meta.label}</strong>
          <em>${category.projects.length} 个目录</em>
          <p>${meta.desc}</p>
        </div>
      </a>`;
  }

  function renderSearch(query) {
    const projects = state.projects.filter((project) =>
      project.name.toLowerCase().includes(query) ||
      project.path.toLowerCase().includes(query) ||
      project.tags.some((tag) => tag.includes(query))
    );
    const fileMatches = state.files.filter((file) => file.name.toLowerCase().includes(query) || file.path.toLowerCase().includes(query));
    const grouped = new Map();
    for (const file of fileMatches.slice(0, 80)) {
      const owner = state.projectByPath.get(ownerPath(file.path));
      if (!owner) continue;
      if (!grouped.has(owner.path)) grouped.set(owner.path, { project: owner, files: [] });
      grouped.get(owner.path).files.push(file);
    }

    els.content.innerHTML = `
      <div class="view-head">
        <div><p class="eyebrow">Search</p><h1>“${escapeHtml(els.search.value.trim())}” 的结果</h1></div>
      </div>
      <section class="section">
        <div class="section-head"><div><h2>匹配项目</h2><p>${projects.length} 个</p></div></div>
        ${projects.length ? `<div class="project-grid">${projects.slice(0, 24).map(projectCard).join("")}</div>` : emptyBlock("没有匹配的项目")}
      </section>
      <section class="section">
        <div class="section-head"><div><h2>按项目归类的文件</h2><p>${fileMatches.length} 个文件匹配，优先显示前 ${Math.min(fileMatches.length, 80)} 个</p></div></div>
        ${grouped.size ? [...grouped.values()].slice(0, 8).map(({ project, files }) => `
          <div class="search-group">
            <div class="section-head"><h3><a href="#/project/${encodeURIComponent(project.path)}">${tagMeta(project.tag).icon} ${escapeHtml(project.name)}</a></h3><a class="text-link" href="#/project/${encodeURIComponent(project.path)}">进入项目 →</a></div>
            <div class="file-grid">${renderFileCards(files.slice(0, 8))}</div>
          </div>
        `).join("") : emptyBlock("没有匹配的文件")}
      </section>
    `;
  }

  function projectsByTag(key) {
    if (key === "all") return state.projects;
    return state.projects.filter((project) => project.tags.includes(key));
  }

  function renderTag(key) {
    const tag = key === "all" ? { key: "all", label: "全部作品", icon: "✦", desc: "按质量与更新时间展示所有项目目录" } : tagMeta(key);
    const projects = key === "all" ? state.projects : projectsByTag(key);
    els.breadcrumbs.innerHTML = `<a href="#/">Outputs</a><span>›</span><span>${tag.icon} ${tag.label}</span>`;
    els.content.innerHTML = `
      <div class="tag-page-head tag-head-${tag.key}">
        <span>${tag.icon}</span>
        <div><h1>${tag.label}</h1><p>${tag.desc} · ${projects.length} 个目录</p></div>
      </div>
      <section class="section">
        ${projects.length ? `<div class="project-grid">${projects.map(projectCardStrip).join("")}</div>` : emptyBlock("该分类下暂无项目")}
      </section>
    `;
  }

  function totalKind(kind) {
    return state.files.filter((file) => kindOf(file) === kind).length;
  }

  function renderCategory(key) {
    const category = state.categories.find((item) => item.key === key);
    if (!category) {
      els.breadcrumbs.innerHTML = breadcrumbHome("分类不存在");
      els.content.innerHTML = emptyBlock("分类可能已被移动或重命名，请刷新后重试。");
      return;
    }
    const meta = categoryMeta(key);
    els.breadcrumbs.innerHTML = `<a href="#/">Outputs</a><span>›</span><span>${meta.icon} ${meta.label}</span>`;
    els.content.innerHTML = `
      <div class="tag-page-head cat-head-${key}" style="--cat-accent:${meta.accent}">
        <span>${meta.icon}</span>
        <div><h1>${meta.label}</h1><p>${meta.desc} · ${category.projects.length} 个目录</p></div>
      </div>
      <section class="section">
        ${category.projects.length ? `<div class="project-grid">${category.projects.map(projectCardStrip).join("")}</div>` : emptyBlock("该分类下暂无项目")}
      </section>
    `;
  }

  function projectCard(project) {
    const tag = tagMeta(project.tag);
    return `
      <a class="project-card" href="#/project/${encodeURIComponent(project.path)}">
        <div class="cover">
          ${project.cover ? `<img loading="lazy" src="${rawUrl(project.cover.path)}" alt="${escapeAttr(project.name)}">` : `<div class="cover-icon">${tag.icon}</div>`}
          <span class="cover-badge">${tag.icon} ${tag.label}</span>
        </div>
        <div class="project-body">
          <h3>${escapeHtml(project.name)}</h3>
          <p>${escapeHtml(kindCountsLine(project))} · ${formatDate(project.mtime)}</p>
          <div class="tag-row">${project.tags.slice(0, 3).map((key) => `<span class="tag">${tagMeta(key).icon} ${tagMeta(key).label}</span>`).join("")}</div>
        </div>
      </a>
    `;
  }

  function projectCardStrip(project) {
    const tag = tagMeta(project.tag);
    const strip = project.thumbnails.slice(0, 4);
    return `
      <a class="project-card project-card-strip" href="#/project/${encodeURIComponent(project.path)}">
        <div class="cover">
          ${project.cover ? `<img loading="lazy" src="${rawUrl(project.cover.path)}" alt="${escapeAttr(project.name)}">` : `<div class="cover-icon">${tag.icon}</div>`}
          <span class="cover-badge">${tag.icon} ${tag.label}</span>
        </div>
        <div class="project-body">
          <h3>${escapeHtml(project.name)}</h3>
          <p>${escapeHtml(kindCountsLine(project))}</p>
          ${strip.length ? `<div class="thumb-strip">${strip.map((file) => `<img loading="lazy" src="${rawUrl(file.path)}" alt="">`).join("")}</div>` : `<div class="tag-row">${project.tags.slice(0, 3).map((key) => `<span class="tag">${tagMeta(key).label}</span>`).join("")}</div>`}
        </div>
      </a>
    `;
  }

  function renderFileCards(files) {
    return files.map((file) => {
      const kind = kindOf(file);
      let thumb = `<div class="file-icon">${kindMeta(kind).icon}</div>`;
      if (kind === "image") thumb = `<img loading="lazy" src="${rawUrl(file.path)}" alt="${escapeAttr(file.name)}">`;
      if (kind === "video") thumb = `<video class="card-video" muted playsinline preload="metadata" src="${rawUrl(file.path)}#t=0.5"></video>`;
      return `
        <a class="file-card" href="#/file/${encodeURIComponent(file.path)}">
          <div class="file-thumb">${thumb}</div>
          <div class="file-meta"><strong>${escapeHtml(file.name)}</strong><small>${kindMeta(kind).label} · ${formatDate(file.mtime)}</small></div>
        </a>
      `;
    }).join("");
  }

  function mediaWall(files, viewKey, initial = 36) {
    const limit = state.limits[viewKey] || initial;
    const visible = files.slice(0, limit);
    return `
      <div class="media-wall">${visible.map((file) => `
        <a class="media-tile image-tile" href="#/file/${encodeURIComponent(file.path)}">
          <img loading="lazy" src="${rawUrl(file.path)}" alt="${escapeAttr(file.name)}" data-lightbox="${escapeAttr(file.path)}">
          <span>${escapeHtml(file.name)}</span>
        </a>`).join("")}
      </div>
      ${loadMoreButton(files.length, limit, viewKey)}
    `;
  }

  function videoWall(files, viewKey, initial = 24) {
    const limit = state.limits[viewKey] || initial;
    const visible = files.slice(0, limit);
    return `
      <div class="video-wall">${visible.map((file) => `
        <a class="video-tile" href="#/file/${encodeURIComponent(file.path)}">
          <video muted playsinline preload="metadata" src="${rawUrl(file.path)}#t=0.5"></video>
          <span class="video-play">▶</span>
          <small>${escapeHtml(file.name)}</small>
        </a>`).join("")}
      </div>
      ${loadMoreButton(files.length, limit, viewKey)}
    `;
  }

  function loadMoreButton(total, limit, viewKey) {
    if (total <= limit) return "";
    return `<button class="primary-btn load-more" data-load-more="${escapeAttr(viewKey)}">加载更多（剩余 ${total - limit} 个）</button>`;
  }

  function kindCountsLine(project) {
    const important = ["video", "image", "audio", "document", "web", "code", "data"];
    return important.filter((kind) => project.counts[kind]).map((kind) => `${project.counts[kind]} ${kindMeta(kind).label}`).join(" · ") || "暂无可分类文件";
  }

  function projectSummaryLine(project) {
    return `${kindCountsLine(project)}；${formatBytes(project.size)}，更新于 ${formatDate(project.mtime)}`;
  }

  function renderProjectOrList(current) {
    const project = state.projectByPath.get(current.path);
    if (!project) {
      els.breadcrumbs.innerHTML = breadcrumbHome("项目不存在");
      els.content.innerHTML = emptyBlock("目录可能已被移动或删除，请刷新后重试。");
      return;
    }
    if (current.kind) {
      renderKindList({
        title: project.name,
        path: project.path,
        files: project.files,
        kind: current.kind,
        routePrefix: `project/${encodeURIComponent(project.path)}`,
        project,
      });
    } else {
      renderProject(project);
    }
  }

  function renderProject(project) {
    const catMeta = project.categoryKey ? categoryMeta(project.categoryKey) : null;
    els.breadcrumbs.innerHTML = `<a href="#/">Outputs</a><span>›</span>` +
      (catMeta
        ? `<a href="#/category/${encodeURIComponent(catMeta.key)}">${catMeta.icon} ${catMeta.label}</a><span>›</span>`
        : "") +
      `<span>${escapeHtml(project.name)}</span>`;
    els.content.innerHTML = `
      <div class="project-layout">
        <section class="panel project-hero">
          <div class="tag-row">${project.tags.map((key) => `<a class="tag tag-link-chip ${key}" href="#/tag/${encodeURIComponent(key)}">${tagMeta(key).icon} ${tagMeta(key).label}</a>`).join("")}</div>
          <h1>${escapeHtml(project.name)}</h1>
          <p class="project-intro" data-meta-path="${project.readme ? escapeAttr(project.readme.path) : ""}" data-meta-field="summary">${escapeHtml(projectSummaryLine(project))}</p>
          <div class="hero-actions">
            ${project.mainWeb ? `<a class="primary-btn" href="${rawUrl(project.mainWeb.path)}" target="_blank" rel="noreferrer">🌐 打开网页</a><a class="ghost-btn" href="#/file/${encodeURIComponent(project.mainWeb.path)}">站内预览网页</a>` : ""}
            ${project.mainVideo ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(project.mainVideo.path)}">🎬 播放主视频</a>` : ""}
            ${project.readme ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(project.readme.path)}">📄 阅读说明</a>` : ""}
          </div>
          <div class="featured">${renderFeatured(project)}</div>
          <div class="kind-nav">${kindNavItems(project).join("")}</div>
          ${quickSection(project, "image", "图片精选", mediaWall(project.images, `project-${project.path}-image`, 12), `#/project/${encodeURIComponent(project.path)}/image`)}
          ${quickSection(project, "video", "视频内容", videoWall(project.videos, `project-${project.path}-video`, 6), `#/project/${encodeURIComponent(project.path)}/video`)}
          ${quickSection(project, "audio", "音频内容", playlistHtml(project.audios.slice(0, 8)), `#/project/${encodeURIComponent(project.path)}/audio`)}
          ${webSection(project)}
          ${quickSection(project, "document", "文档", `<div class="file-grid">${renderFileCards(project.docs.slice(0, 6))}</div>`, `#/project/${encodeURIComponent(project.path)}/document`)}
          ${codeSection(project)}
          ${quickSection(project, "data", "数据与实验", `<div class="file-grid">${renderFileCards(project.data.slice(0, 8))}</div>`, `#/project/${encodeURIComponent(project.path)}/data`)}
        </section>
        <aside class="panel tree-panel"><h2>文件目录</h2>${renderTree(project.node, project.path)}</aside>
      </div>
    `;
    hydrateMetas(els.content);
  }

  function kindNavItems(project) {
    return KINDS.filter((kind) => project.counts[kind.key]).map((kind) => `
      <a class="kind-nav-item" href="#/project/${encodeURIComponent(project.path)}/${kind.key}">
        <strong>${kind.icon} ${project.counts[kind.key]}</strong><span>${kind.label}</span>
      </a>
    `);
  }

  function quickSection(project, kind, title, body, moreHref) {
    if (!project.counts[kind]) return "";
    return `
      <div class="subsection">
        <div class="section-head compact-head"><h2>${title} <small>${project.counts[kind]}</small></h2><a class="text-link" href="${moreHref}">查看全部 →</a></div>
        ${body}
      </div>
    `;
  }

  function webSection(project) {
    if (!project.webs.length) return "";
    return `
      <div class="subsection">
        <div class="section-head compact-head"><h2>网页入口 <small>${project.webs.length}</small></h2>${project.mainWeb ? `<a class="text-link" href="#/project/${encodeURIComponent(project.path)}/web">查看全部 →</a>` : ""}</div>
        <div class="insight-grid">${project.webs.slice(0, 8).map((file) => `
          <a class="insight-card" href="#/file/${encodeURIComponent(file.path)}">
            <span class="insight-icon">🌐</span>
            <strong data-meta-path="${escapeAttr(file.path)}" data-meta-field="title">${escapeHtml(file.name)}</strong>
            <p data-meta-path="${escapeAttr(file.path)}" data-meta-field="summary">${escapeHtml(file.path)}</p>
            <span class="insight-actions"><em>站内预览</em><b data-open-html="${escapeAttr(file.path)}">新窗口打开 ↗</b></span>
          </a>`).join("")}
        </div>
      </div>
    `;
  }

  function codeSection(project) {
    if (!project.code.length) return "";
    const files = project.code.filter((file) => file.path.split("/").length - 1 <= 2).sort((a, b) => b.mtime - a.mtime).slice(0, 6);
    return `
      <div class="subsection">
        <div class="section-head compact-head"><h2>代码功能 <small>${project.code.length}</small></h2><a class="text-link" href="#/project/${encodeURIComponent(project.path)}/code">查看全部 →</a></div>
        <div class="insight-grid">${files.map((file) => `
          <a class="insight-card" href="#/file/${encodeURIComponent(file.path)}">
            <span class="insight-icon">${codeIcon(file)}</span>
            <strong>${escapeHtml(file.name)}</strong>
            <p data-meta-path="${escapeAttr(file.path)}" data-meta-field="summary">正在读取功能简介…</p>
            <small>${kindMeta("code").label} · ${formatBytes(file.size)}</small>
          </a>`).join("")}
        </div>
      </div>
    `;
  }

  function renderFeatured(project) {
    if (project.mainWeb) return `<iframe src="${rawUrl(project.mainWeb.path)}" sandbox="allow-scripts allow-forms allow-popups allow-same-origin" loading="lazy" title="${escapeAttr(project.mainWeb.name)}"></iframe>`;
    if (project.mainVideo) return `<video controls preload="metadata" src="${rawUrl(project.mainVideo.path)}#t=0.1"></video>`;
    if (project.mainAudio) return `<audio controls preload="metadata" src="${rawUrl(project.mainAudio.path)}"></audio>`;
    if (project.cover) return `<img data-lightbox="${escapeAttr(project.cover.path)}" src="${rawUrl(project.cover.path)}" alt="${escapeAttr(project.cover.name)}">`;
    return `<div class="featured-placeholder"><div><span>${tagMeta(project.tag).icon}</span><p>该项目暂无可预览的媒体</p></div></div>`;
  }

  function playlistHtml(files) {
    return `<div class="playlist">${files.map((file) => `
      <a class="playlist-item" href="#/file/${encodeURIComponent(file.path)}"><span>🎵</span><span>${escapeHtml(file.name)}</span><small>${formatBytes(file.size)}</small></a>
    `).join("")}</div>`;
  }

  function renderDirOrList(current) {
    const node = state.nodeByPath.get(current.path);
    if (!node || node.type !== "directory") {
      els.breadcrumbs.innerHTML = breadcrumbHome("目录不存在");
      els.content.innerHTML = emptyBlock("目录可能已被移动或删除，请刷新后重试。");
      return;
    }
    const owner = state.projectByPath.get(ownerPath(current.path));
    if (current.kind) {
      renderKindList({
        title: node.name,
        files: collectFiles(node),
        kind: current.kind,
        routePrefix: `dir/${current.path.split("/").map(encodeURIComponent).join("/")}`,
        project: owner,
      });
    } else {
      renderDirectory(node, owner);
    }
  }

  function renderDirectory(node, ownerProject) {
    const files = collectFiles(node);
    const counts = {};
    files.forEach((file) => {
      const kind = kindOf(file);
      counts[kind] = (counts[kind] || 0) + 1;
    });
    const subfolders = (node.children || []).filter((child) => child.type === "directory");
    const routeBase = `dir/${node.path.split("/").map(encodeURIComponent).join("/")}`;
    const pathParts = node.path ? node.path.split("/") : [];
    const crumbs = pathParts.slice(0, -1).map(crumbLink).join("<span>›</span>");
    els.breadcrumbs.innerHTML = `<a href="#/">Outputs</a><span>›</span>${crumbs ? `${crumbs}<span>›</span>` : ""}<span>${escapeHtml(node.name)}</span>`;

    els.content.innerHTML = `
      <div class="project-layout">
        <section class="panel project-hero">
          <div class="tag-row">${KINDS.filter((kind) => counts[kind.key]).map((kind) => `<a class="tag tag-link-chip" href="#/${routeBase}/${kind.key}">${kind.icon} ${kind.label} ${counts[kind.key]}</a>`).join("")}</div>
          <h1>📁 ${escapeHtml(node.name)}</h1>
          <p>${files.length} 个文件 · ${formatBytes(files.reduce((sum, file) => sum + file.size, 0))} · 更新于 ${formatDate(node.mtime)}</p>
          ${subfolders.length ? `
            <div class="subsection">
              <div class="section-head compact-head"><h2>子目录</h2></div>
              <div class="folder-grid">${subfolders.map(folderCard).join("")}</div>
            </div>` : ""}
          ${directoryKindSection(node, "image", "图片", counts, routeBase)}
          ${directoryKindSection(node, "video", "视频", counts, routeBase)}
          ${directoryKindSection(node, "audio", "音频", counts, routeBase)}
          ${directoryKindSection(node, "web", "网页", counts, routeBase)}
          ${directoryKindSection(node, "document", "文档", counts, routeBase)}
          ${directoryKindSection(node, "code", "代码", counts, routeBase)}
          ${directoryKindSection(node, "data", "数据", counts, routeBase)}
        </section>
        <aside class="panel tree-panel"><h2>项目目录</h2>${ownerProject ? renderTree(ownerProject.node, ownerProject.path) : renderTree(node, node.path)}</aside>
      </div>
    `;
    hydrateMetas(els.content);
  }

  function crumbLink(part, index, parts) {
    const path = parts.slice(0, index + 1).join("/");
    return `<a href="#/dir/${path.split("/").map(encodeURIComponent).join("/")}">${escapeHtml(part)}</a>`;
  }

  function folderCard(node) {
    const files = collectFiles(node);
    const image = chooseCover(files.filter((file) => kindOf(file) === "image"));
    const tags = KINDS.map((kind) => ({ kind: kind.key, count: files.filter((file) => kindOf(file) === kind.key).length })).filter((item) => item.count).slice(0, 4);
    return `
      <a class="folder-card" href="#/dir/${node.path.split("/").map(encodeURIComponent).join("/")}">
        <div class="folder-cover">${image ? `<img loading="lazy" src="${rawUrl(image.path)}" alt="">` : `<span>📁</span>`}</div>
        <strong>${escapeHtml(humanizeName(node.name))}</strong>
        <small>${files.length} 个文件${tags.length ? ` · ${tags.map((item) => `${item.count}${kindMeta(item.kind).label}`).join("、")}` : ""}</small>
      </a>
    `;
  }

  function directoryKindSection(node, kind, title, counts, routeBase) {
    if (!counts[kind]) return "";
    const files = collectFiles(node).filter((file) => kindOf(file) === kind).sort(comparePaths);
    const viewKey = `dir-${node.path}-${kind}`;
    let body = `<div class="file-grid">${renderFileCards(files.slice(0, 8))}</div>`;
    if (kind === "image") body = mediaWall(files, viewKey, 12);
    if (kind === "video") body = videoWall(files, viewKey, 6);
    if (kind === "audio") body = playlistHtml(files.slice(0, 8));
    if (kind === "web") body = `<div class="insight-grid">${files.slice(0, 6).map(webInsightCard).join("")}</div>`;
    if (kind === "code") body = `<div class="insight-grid">${files.slice(0, 6).map(codeInsightCard).join("")}</div>`;
    return `
      <div class="subsection">
        <div class="section-head compact-head"><h2>${title} <small>${counts[kind]}</small></h2><a class="text-link" href="#/${routeBase}/${kind}">查看全部 →</a></div>
        ${body}
      </div>
    `;
  }

  function renderKindList({ title, files, kind, routePrefix }) {
    const meta = kindMeta(kind);
    const kindFiles = files.filter((file) => kindOf(file) === kind).sort(comparePaths);
    const counts = {};
    files.forEach((file) => {
      const itemKind = kindOf(file);
      counts[itemKind] = (counts[itemKind] || 0) + 1;
    });
    const viewKey = `${routePrefix}-${kind}`;
    let body = "";
    if (kind === "image") body = mediaWall(kindFiles, viewKey, 48);
    else if (kind === "video") body = videoWall(kindFiles, viewKey, 30);
    else if (kind === "audio") body = playlistHtml(kindFiles);
    else if (kind === "web") body = `<div class="insight-grid wide-grid">${kindFiles.map(webInsightCard).join("")}</div>`;
    else if (kind === "code") body = `<div class="insight-grid wide-grid">${kindFiles.map(codeInsightCard).join("")}</div>`;
    else {
      const limit = state.limits[viewKey] || 90;
      body = `<div class="file-grid dense-file-grid">${renderFileCards(kindFiles.slice(0, limit))}</div>${loadMoreButton(kindFiles.length, limit, viewKey)}`;
    }

    els.breadcrumbs.innerHTML = `<a href="#/">Outputs</a><span>›</span><span>${escapeHtml(title)}</span><span>›</span><span>${meta.icon} ${meta.label}</span>`;
    els.content.innerHTML = `
      <div class="browse-page panel">
        <div class="browse-head">
          <div><h1>${meta.icon} ${meta.label}</h1><p>${kindFiles.length} 个文件</p></div>
        </div>
        <div class="chip-row browse-chips">
          ${KINDS.filter((item) => counts[item.key]).map((item) => `<a class="chip ${item.key === kind ? "active" : ""}" href="#/${routePrefix}/${item.key}">${item.icon} ${item.label} ${counts[item.key]}</a>`).join("")}
        </div>
        ${kindFiles.length ? body : emptyBlock(`该目录下暂无${meta.label}`)}
      </div>
    `;
    hydrateMetas(els.content);
  }

  function webInsightCard(file) {
    return `
      <a class="insight-card" href="#/file/${encodeURIComponent(file.path)}">
        <span class="insight-icon">🌐</span>
        <strong data-meta-path="${escapeAttr(file.path)}" data-meta-field="title">${escapeHtml(file.name)}</strong>
        <p data-meta-path="${escapeAttr(file.path)}" data-meta-field="summary">${escapeHtml(file.path)}</p>
        <span class="insight-actions"><em>站内预览</em><b data-open-html="${escapeAttr(file.path)}">新窗口打开 ↗</b></span>
      </a>`;
  }

  function codeInsightCard(file) {
    return `
      <a class="insight-card" href="#/file/${encodeURIComponent(file.path)}">
        <span class="insight-icon">${codeIcon(file)}</span>
        <strong>${escapeHtml(file.name)}</strong>
        <p data-meta-path="${escapeAttr(file.path)}" data-meta-field="summary">正在读取功能简介…</p>
        <small>${formatBytes(file.size)} · ${formatDate(file.mtime)}</small>
      </a>`;
  }

  function renderFile(path) {
    const file = state.fileByPath.get(path);
    if (!file) {
      els.breadcrumbs.innerHTML = breadcrumbHome("文件不存在");
      els.content.innerHTML = emptyBlock("文件可能已被移动或删除，请刷新后重试。");
      return;
    }
    const ownerKey = ownerPath(file.path);
    const project = state.projectByPath.get(ownerKey);
    const kind = kindOf(file);
    const siblings = project ? project.files.filter((item) => kindOf(item) === kind) : [file];
    const index = siblings.findIndex((item) => item.path === file.path);
    const prev = index > 0 ? siblings[index - 1] : null;
    const next = index >= 0 && index < siblings.length - 1 ? siblings[index + 1] : null;

    const fileCat = project?.categoryKey ? categoryMeta(project.categoryKey) : null;
    els.breadcrumbs.innerHTML = `
      <a href="#/">Outputs</a><span>›</span>
      ${fileCat ? `<a href="#/category/${encodeURIComponent(fileCat.key)}">${fileCat.icon} ${fileCat.label}</a><span>›</span>` : ""}
      ${project ? `<a href="#/project/${encodeURIComponent(project.path)}">${escapeHtml(project.name)}</a><span>›</span>` : ""}
      <span>${escapeHtml(file.name)}</span>`;

    els.content.innerHTML = `
      <div class="viewer">
        <section class="panel viewer-main">
          <header class="viewer-header">
            <div><h1>${kindMeta(kind).icon} ${escapeHtml(file.name)}</h1><small>${escapeHtml(file.path)} · ${formatBytes(file.size)} · ${formatDate(file.mtime)}</small></div>
            <a class="ghost-btn" href="${rawUrl(file.path)}" target="_blank" rel="noreferrer">新窗口打开</a>
          </header>
          <div class="viewer-stage" id="viewerStage">${stagePlaceholder(file)}</div>
          <div class="viewer-toolbar">
            ${prev ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(prev.path)}">‹ 上一个</a>` : `<button class="ghost-btn" disabled>‹ 上一个</button>`}
            <a class="ghost-btn" href="${rawUrl(file.path)}" download="${escapeAttr(file.name)}">下载</a>
            ${next ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(next.path)}">下一个 ›</a>` : `<button class="ghost-btn" disabled>下一个 ›</button>`}
          </div>
        </section>
        <aside class="panel tree-panel">
          ${["image", "video", "audio"].includes(kind) ? `<h2>${kindMeta(kind).label}列表</h2><div class="playlist compact-playlist">${siblings.slice(Math.max(0, index - 12), index + 13).map((item) => `<a class="playlist-item ${item.path === file.path ? "active" : ""}" href="#/file/${encodeURIComponent(item.path)}"><span>${kindMeta(kind).icon}</span><span>${escapeHtml(item.name)}</span></a>`).join("")}</div>` : ""}
          <h2>${project ? "文件目录" : "文件信息"}</h2>
          ${project ? renderTree(project.node, project.path, file.path) : ""}
        </aside>
      </div>
    `;
    hydrateFile(file, kind);
  }

  function stagePlaceholder(file) {
    const kind = kindOf(file);
    if (kind === "image") return `<img data-lightbox="${escapeAttr(file.path)}" src="${rawUrl(file.path)}" alt="${escapeAttr(file.name)}">`;
    if (kind === "video") return `<video controls preload="metadata" src="${rawUrl(file.path)}#t=0.01"></video>`;
    if (kind === "audio") return `<audio controls preload="metadata" src="${rawUrl(file.path)}"></audio>`;
    if (kind === "web") return `<iframe src="${rawUrl(file.path)}" sandbox="allow-scripts allow-forms allow-popups allow-same-origin" title="${escapeAttr(file.name)}"></iframe>`;
    if (file.ext === "pdf") return `<iframe src="${rawUrl(file.path)}" title="${escapeAttr(file.name)}"></iframe>`;
    if (TEXT_EXTS.has(file.ext)) return `<div class="loading">正在读取文件内容</div>`;
    return `<div class="stage-empty"><div><span>📦</span><p>暂不支持内嵌预览此格式，请下载或在系统中打开。</p><a class="primary-btn" href="${rawUrl(file.path)}" target="_blank" rel="noreferrer">打开文件</a></div></div>`;
  }

  async function hydrateFile(file, kind) {
    const stage = document.getElementById("viewerStage");
    if (!stage || !TEXT_EXTS.has(file.ext)) return;
    const text = await fetchText(file.path);
    if (text == null) {
      stage.innerHTML = stageEmpty("无法按文本读取该文件");
      return;
    }
    if (file.ext === "md") {
      stage.className = "viewer-stage markdown";
      stage.innerHTML = renderMarkdown(text, file.path);
      return;
    }

    let displayed = text;
    if (file.ext === "json") {
      try { displayed = JSON.stringify(JSON.parse(text), null, 2); } catch { /* show raw text */ }
    }
    const lines = displayed.replace(/\n$/, "").split("\n");
    const limited = lines.length > 5000;
    const visibleLines = limited ? lines.slice(0, 5000) : lines;
    const meta = kind === "code" ? await getMeta(file.path) : null;
    stage.className = "viewer-stage";
    stage.innerHTML = `
      ${kind === "code" ? `
        <div class="code-summary">
          <p>${escapeHtml(meta?.summary || `${file.ext} 脚本 · ${lines.length} 行 · ${formatBytes(file.size)}`)}</p>
          ${meta?.definitions?.length ? `<div class="definition-list">${meta.definitions.slice(0, 28).map((name) => `<span class="definition">${escapeHtml(name)}</span>`).join("")}</div>` : ""}
        </div>` : `<div class="code-summary"><p>${escapeHtml(`${file.ext || "unknown"} 文本文件 · ${lines.length} 行`)}</p></div>`}
      <div class="code-wrap"><pre class="code-block">${visibleLines.map((line, index) => `<span class="code-line"><span class="line-number">${index + 1}</span><code class="line-code">${highlightLine(line, file.ext)}</code></span>`).join("")}</pre></div>
      ${limited ? `<div class="code-summary"><p>文件较大，仅预览前 5000 行，请下载查看完整内容。</p></div>` : ""}
    `;
  }

  function renderTree(node, ownerPath, activePath = "") {
    const children = (node.children || []).slice().sort((a, b) => {
      if ((a.type === "directory") !== (b.type === "directory")) return a.type === "directory" ? -1 : 1;
      return a.name.localeCompare(b.name, "zh-Hans-CN", { numeric: true, sensitivity: "base" });
    });
    return `<div class="tree"><ul>${children.map((child) => {
      if (child.type === "directory") {
        const expanded = !activePath || activePath === child.path || activePath.startsWith(child.path + "/");
        return `<li class="folder ${expanded ? "" : "collapsed"}"><span class="tree-caret" data-folder>▾</span><a href="#/dir/${child.path.split("/").map(encodeURIComponent).join("/")}">📁 ${escapeHtml(child.name)}</a>${renderTree(child, ownerPath, activePath)}</li>`;
      }
      return `<li><a class="tree-file ${activePath === child.path ? "active" : ""}" href="#/file/${encodeURIComponent(child.path)}" title="${escapeAttr(child.path)}"><span>${kindMeta(kindOf(child)).icon}</span><span>${escapeHtml(child.name)}</span></a></li>`;
    }).join("")}</ul></div>`;
  }

  async function getMeta(path) {
    if (state.metas.has(path)) return state.metas.get(path);
    await ensureMetas([path]);
    return state.metas.get(path);
  }

  async function ensureMetas(paths) {
    const unique = [...new Set(paths.filter(Boolean))].filter((path) => !state.metas.has(path));
    if (!unique.length) return;
    unique.forEach((path) => state.metas.set(path, null));
    for (let index = 0; index < unique.length; index += 100) {
      const batch = unique.slice(index, index + 100);
      try {
        const data = await fetchJson("/api/meta", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths: batch }),
        });
        Object.entries(data.items || {}).forEach(([path, meta]) => state.metas.set(path, meta));
      } catch {
        batch.forEach((path) => state.metas.set(path, null));
      }
    }
  }

  async function hydrateMetas(root) {
    if (!root) return;
    const nodes = [...root.querySelectorAll("[data-meta-path]")];
    const paths = nodes.map((node) => node.dataset.metaPath).filter(Boolean);
    await ensureMetas(paths);
    for (const node of nodes) {
      const meta = state.metas.get(node.dataset.metaPath);
      const value = meta?.[node.dataset.metaField || "summary"];
      if (value) node.textContent = value;
    }
  }

  async function fetchText(path) {
    try {
      const response = await fetch(rawUrl(path), { cache: "no-store" });
      if (!response.ok) return null;
      return await response.text();
    } catch {
      return null;
    }
  }

  const lightboxState = { files: [], index: 0 };

  function handleGlobalClick(event) {
    const more = event.target.closest("[data-load-more]");
    if (more) {
      event.preventDefault();
      const key = more.dataset.loadMore;
      state.limits[key] = (state.limits[key] || (key.includes("video") ? 24 : 36)) + (key.includes("video") ? 24 : 48);
      render();
      return;
    }
    const caret = event.target.closest("[data-folder]");
    if (caret) {
      event.preventDefault();
      caret.closest(".folder").classList.toggle("collapsed");
      return;
    }
    const openHtml = event.target.closest("[data-open-html]");
    if (openHtml) {
      event.preventDefault();
      window.open(rawUrl(openHtml.dataset.openHtml), "_blank", "noopener,noreferrer");
      return;
    }
    const image = event.target.closest("[data-lightbox]");
    if (image) {
      event.preventDefault();
      const wall = image.closest(".media-wall");
      const tiles = wall ? [...wall.querySelectorAll(".image-tile img[data-lightbox]")] : [image];
      lightboxState.files = tiles.map((node) => state.fileByPath.get(node.dataset.lightbox)).filter(Boolean);
      lightboxState.index = Math.max(0, lightboxState.files.findIndex((file) => file.path === image.dataset.lightbox));
      updateLightbox();
      els.lightbox.hidden = false;
    }
  }

  function closeLightbox() { els.lightbox.hidden = true; }
  function moveLightbox(direction) {
    if (!lightboxState.files.length) return;
    lightboxState.index = (lightboxState.index + direction + lightboxState.files.length) % lightboxState.files.length;
    updateLightbox();
  }
  function updateLightbox() {
    const file = lightboxState.files[lightboxState.index];
    if (file) {
      els.lightboxImage.src = rawUrl(file.path);
      els.lightboxImage.alt = file.name;
    }
  }

  function renderMarkdown(markdown, filePath) {
    const blocks = [];
    const storeBlock = (html) => {
      const id = `@@MARKDOWN_BLOCK_${blocks.length}@@`;
      blocks.push(html);
      return id;
    };
    const source = markdown.replace(/\r\n?/g, "\n");
    const withoutFences = source.replace(/```([^\n`]*)\n?([\s\S]*?)```/g, (_match, lang, code) =>
      storeBlock(`<pre><code data-lang="${escapeAttr(lang.trim())}">${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`));
    const lines = withoutFences.split("\n");
    const htmlLines = [];
    let listType = null;
    const quote = [];
    const paragraph = [];
    const flushParagraph = () => {
      if (paragraph.length) {
        htmlLines.push(`<p>${paragraph.map((line) => inlineMarkdown(line, filePath)).join("<br>")}</p>`);
        paragraph.length = 0;
      }
    };
    const flushQuote = () => {
      if (quote.length) {
        htmlLines.push(`<blockquote>${quote.map((line) => inlineMarkdown(line, filePath)).join("<br>")}</blockquote>`);
        quote.length = 0;
      }
    };
    const closeList = () => {
      if (listType) {
        htmlLines.push(`</${listType}>`);
        listType = null;
      }
    };

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();
      if (!trimmed) { flushParagraph(); flushQuote(); closeList(); continue; }
      if (trimmed.startsWith("@@MARKDOWN_BLOCK_")) { flushParagraph(); flushQuote(); closeList(); htmlLines.push(trimmed); continue; }
      const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph(); flushQuote(); closeList();
        const level = heading[1].length;
        htmlLines.push(`<h${level} id="${slugify(heading[2])}">${inlineMarkdown(heading[2], filePath)}</h${level}>`);
        continue;
      }
      if (/^(\*\*\*|---)\s*$/.test(trimmed)) { flushParagraph(); flushQuote(); closeList(); htmlLines.push("<hr>"); continue; }
      if (trimmed.startsWith(">")) { flushParagraph(); closeList(); quote.push(trimmed.replace(/^>\s?/, "")); continue; }
      if (trimmed.includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[index + 1])) {
        flushParagraph(); flushQuote(); closeList();
        const headers = splitMarkdownRow(trimmed);
        const rows = [];
        index += 2;
        while (index < lines.length && lines[index].includes("|")) { rows.push(splitMarkdownRow(lines[index])); index += 1; }
        index -= 1;
        htmlLines.push(`<table><thead><tr>${headers.map((cell) => `<th>${inlineMarkdown(cell, filePath)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell, filePath)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
        continue;
      }
      const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
      const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (unordered || ordered) {
        flushParagraph(); flushQuote();
        const nextType = unordered ? "ul" : "ol";
        if (listType !== nextType) { closeList(); listType = nextType; htmlLines.push(`<${listType}>`); }
        htmlLines.push(`<li>${inlineMarkdown((unordered || ordered)[1], filePath)}</li>`);
        continue;
      }
      flushQuote(); closeList(); paragraph.push(trimmed);
    }
    flushParagraph(); flushQuote(); closeList();
    return htmlLines.join("\n").replace(/@@MARKDOWN_BLOCK_(\d+)@@/g, (_match, index) => blocks[Number(index)]);
  }

  function splitMarkdownRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
  }

  function inlineMarkdown(input, filePath) {
    let text = escapeHtml(input);
    const codeTokens = [];
    text = text.replace(/`([^`]+)`/g, (_match, code) => {
      const id = `@@IC_${codeTokens.length}@@`;
      codeTokens.push(`<code>${code}</code>`);
      return id;
    });
    text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, (_match, alt, href) =>
      `<img src="${markdownUrl(href, filePath, true)}" alt="${alt}" loading="lazy">`);
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, (_match, label, href) => {
      const url = markdownUrl(href, filePath, false);
      const external = /^(https?:|mailto:|\/raw\/)/.test(url);
      return `<a href="${url}" ${external ? 'target="_blank" rel="noreferrer"' : ""}>${label}</a>`;
    });
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    text = text.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    return text.replace(/@@IC_(\d+)@@/g, (_match, index) => codeTokens[Number(index)]);
  }

  function markdownUrl(href, filePath, isMedia) {
    if (!href || href.startsWith("javascript:")) return "#";
    if (/^(https?:|mailto:|data:|#)/.test(href)) return href;
    const baseDir = filePath.includes("/") ? filePath.slice(0, filePath.lastIndexOf("/")) : "";
    const resolved = new URL(href, `http://dashboard.local/${baseDir ? `${baseDir}/` : ""}`).pathname.replace(/^\/+/, "");
    if (!isMedia && /\.md(?:#.*)?$/i.test(resolved)) return `#/file/${encodeURIComponent(resolved)}`;
    return rawUrl(resolved);
  }

  function highlightLine(line, ext) {
    const isPythonLike = ext === "py" || ext === "sh" || ext === "yaml" || ext === "yml";
    const patterns = [/"(?:\\.|[^"\\])*"/, /'(?:\\.|[^'\\])*'/, /`(?:\\.|[^`\\])*`/, /\/\*.*?\*\//, /\/\/[^\n]*/];
    if (isPythonLike) patterns.push(/#[^\n]*/);
    const tokenRegex = new RegExp(patterns.map((pattern) => `(${pattern.source})`).join("|"), "g");
    const keywordSets = {
      py: ["def", "class", "return", "import", "from", "if", "elif", "else", "for", "while", "try", "except", "finally", "with", "as", "async", "await", "lambda", "in", "not", "and", "or", "None", "True", "False", "raise", "yield"],
      js: ["function", "class", "return", "import", "export", "from", "if", "else", "for", "while", "try", "catch", "finally", "const", "let", "var", "async", "await", "new", "extends", "super", "this", "null", "undefined", "true", "false"],
      sh: ["if", "then", "else", "fi", "for", "in", "do", "done", "while", "case", "esac", "function", "return", "export"],
    };
    const words = keywordSets[ext] || (ext === "css" ? [] : keywordSets.js);
    const highlightPlain = (value) => {
      let html = escapeHtml(value);
      if (words.length) html = html.replace(new RegExp(`\\b(${words.join("|")})\\b`, "g"), '<span class="token-keyword">$1</span>');
      return html.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="token-number">$1</span>');
    };
    let result = "";
    let lastIndex = 0;
    let match;
    while ((match = tokenRegex.exec(line)) !== null) {
      result += highlightPlain(line.slice(lastIndex, match.index));
      const isString = match[0].startsWith('"') || match[0].startsWith("'") || match[0].startsWith("`");
      result += `<span class="${isString ? "token-string" : "token-comment"}">${escapeHtml(match[0])}</span>`;
      lastIndex = tokenRegex.lastIndex;
    }
    return result + highlightPlain(line.slice(lastIndex)) || " ";
  }

  function rawUrl(path) {
    return "/raw/" + path.split("/").map(encodeURIComponent).join("/");
  }

  function codeIcon(file) {
    if (file.ext === "py") return "🐍";
    if (file.ext === "js") return "JS";
    if (file.ext === "css") return "🎨";
    if (file.ext === "sh") return "⌘";
    return kindMeta("code").icon;
  }

  function humanizeName(name) {
    if (name === "__root__") return "根目录散文件";
    return name.replace(/[-_]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()).trim();
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "-";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
    return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
  }

  function formatDate(timestamp) {
    if (!timestamp) return "未知时间";
    return new Date(timestamp * 1000).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  }

  function slugify(text) {
    return escapeHtml(text).toLowerCase().replace(/<[^>]+>/g, "").replace(/[^\w\u4e00-\u9fa5-]+/g, "-").replace(/^-+|-+$/g, "") || "section";
  }

  function breadcrumbHome(label) {
    return `<a href="#/">Outputs</a><span>›</span><span>${escapeHtml(label)}</span>`;
  }

  function stageEmpty(message) {
    return `<div class="stage-empty"><div><span>📄</span><p>${escapeHtml(message)}</p></div></div>`;
  }

  function emptyBlock(message) {
    return `<div class="empty">${escapeHtml(message)}</div>`;
  }

  function toast(message) {
    els.toast.textContent = message;
    els.toast.hidden = false;
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => { els.toast.hidden = true; }, 2600);
  }

  function escapeHtml(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }
})();
