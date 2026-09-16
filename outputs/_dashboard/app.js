(() => {
  "use strict";

  const CATEGORIES = [
    { key: "video", label: "视频", icon: "🎬", exts: ["mp4", "webm", "mov", "mkv", "avi", "m4v"] },
    { key: "image", label: "图片", icon: "🖼️", exts: ["jpg", "jpeg", "png", "gif", "webp", "svg", "avif", "bmp"] },
    { key: "audio", label: "音频", icon: "🎵", exts: ["mp3", "wav", "m4a", "flac", "ogg", "aac"] },
    { key: "document", label: "文档", icon: "📄", exts: ["md", "txt", "pdf", "docx"] },
    { key: "web", label: "网页", icon: "🌐", exts: ["html", "htm"] },
    { key: "code", label: "代码", icon: "⌘", exts: ["py", "js", "css", "sh", "ts", "tsx", "jsx", "sql", "yaml", "yml"] },
    { key: "data", label: "数据", icon: "⚙️", exts: ["json", "csv", "tsv", "xml", "toml"] },
    { key: "log", label: "日志", icon: "📝", exts: ["log"] },
  ];

  const TEXT_EXTS = new Set([
    "md", "txt", "pdf", "html", "htm", "py", "js", "css", "sh", "ts", "tsx", "jsx", "sql",
    "yaml", "yml", "json", "csv", "tsv", "xml", "toml", "log", "svg",
  ]);

  const state = {
    root: null,
    files: [],
    projects: [],
    projectByPath: new Map(),
    fileByPath: new Map(),
    category: "all",
    query: "",
    signature: "",
    lightboxFiles: [],
    lightboxIndex: 0,
  };

  const els = {};

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    Object.assign(els, {
      content: document.getElementById("content"),
      categoryNav: document.getElementById("categoryNav"),
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
      if (!isHomeRoute()) location.hash = "#/";
      else render();
    });
    window.addEventListener("hashchange", render);
    window.setInterval(pollTree, 15000);

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

    loadTree(false);
  }

  async function loadTree(manual) {
    try {
      els.scanStatus.textContent = "正在扫描…";
      const response = await fetch("/api/tree", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const root = await response.json();
      const signature = JSON.stringify({
        files: countTree(root),
        mtime: root.mtime,
        size: root.size,
      });
      const changed = signature !== state.signature;
      state.root = root;
      state.signature = signature;
      indexTree(root);
      render();
      if (manual && changed) toast("已同步 outputs 目录");
      els.scanStatus.textContent = `${state.files.length} 个文件 · 实时扫描`;
    } catch (error) {
      els.scanStatus.textContent = "扫描失败";
      els.content.innerHTML = `<div class="empty"><div><h2>无法读取目录</h2><p>请通过启动脚本访问本地服务，而不是直接双击 HTML。</p><pre>${escapeHtml(error.message)}</pre></div></div>`;
    }
  }

  async function pollTree() {
    if (!els.autoRefresh.checked) return;
    try {
      const response = await fetch("/api/tree", { cache: "no-store" });
      if (!response.ok) return;
      const root = await response.json();
      const signature = JSON.stringify({ files: countTree(root), mtime: root.mtime, size: root.size });
      if (state.root && signature !== state.signature) {
        state.root = root;
        state.signature = signature;
        indexTree(root);
        render();
        toast("检测到新内容，已自动同步");
      }
    } catch {
      // offline polling is best effort
    }
  }

  function countTree(node) {
    if (node.type === "file") return 1;
    return (node.children || []).reduce((sum, child) => sum + countTree(child), 0);
  }

  function indexTree(root) {
    const files = [];
    const walk = (node) => {
      if (node.type === "file") {
        files.push(node);
        return;
      }
      ;(node.children || []).forEach(walk);
    };
    walk(root);
    files.sort((a, b) => a.path.localeCompare(b.path, "zh-Hans-CN", { numeric: true, sensitivity: "base" }));

    state.files = files;
    state.fileByPath = new Map(files.map((file) => [file.path, file]));

    const rootFiles = (root.children || []).filter((node) => node.type === "file");
    const projects = [];
    if (rootFiles.length) {
      projects.push(makeProject({
        type: "directory",
        name: "根目录散文件",
        path: "__root__",
        synthetic: true,
        children: rootFiles,
        mtime: Math.max(...rootFiles.map((file) => file.mtime)),
        size: rootFiles.reduce((sum, file) => sum + file.size, 0),
      }));
    }
    for (const node of (root.children || [])) {
      if (node.type === "directory") projects.push(makeProject(node));
    }
    projects.sort((a, b) => b.mtime - a.mtime || a.name.localeCompare(b.name, "zh-Hans-CN"));
    state.projects = projects;
    state.projectByPath = new Map(projects.map((project) => [project.path, project]));
  }

  function makeProject(node) {
    const files = collectFiles(node).sort((a, b) =>
      a.path.localeCompare(b.path, "zh-Hans-CN", { numeric: true, sensitivity: "base" })
    );
    const counts = {};
    for (const file of files) {
      const category = categoryOf(file);
      counts[category] = (counts[category] || 0) + 1;
    }

    const images = files.filter((file) => categoryOf(file) === "image");
    const videos = files.filter((file) => categoryOf(file) === "video");
    const audios = files.filter((file) => categoryOf(file) === "audio");
    const webs = files.filter((file) => categoryOf(file) === "web");
    const docs = files.filter((file) => categoryOf(file) === "document");
    const code = files.filter((file) => categoryOf(file) === "code");
    const data = files.filter((file) => categoryOf(file) === "data");
    const cover = chooseCover(images);
    const mainVideo = chooseMainVideo(videos);
    const mainAudio = audios.sort((a, b) => b.size - a.size)[0];
    const mainWeb = chooseMainWeb(webs, node.name);
    const mainDoc = chooseMainDoc(docs, node.name);
    const primary = inferPrimary(node.name, counts, webs, code);
    const tags = CATEGORIES.filter((category) => counts[category.key]).map((category) => category.key);

    return {
      node,
      name: humanizeName(node.name),
      path: node.path,
      synthetic: Boolean(node.synthetic),
      files,
      counts,
      tags,
      primary,
      cover,
      mainVideo,
      mainAudio,
      mainWeb,
      mainDoc,
      readme: chooseReadme(docs),
      code,
      data,
      images,
      videos,
      audios,
      docs,
      webs,
      size: node.size || files.reduce((sum, file) => sum + file.size, 0),
      mtime: node.mtime || 0,
    };
  }

  function collectFiles(node) {
    if (node.type === "file") return [node];
    return (node.children || []).flatMap(collectFiles);
  }

  function categoryOf(file) {
    const ext = (file.ext || "").toLowerCase();
    const category = CATEGORIES.find((item) => item.exts.includes(ext));
    return category ? category.key : "other";
  }

  function categoryMeta(key) {
    return CATEGORIES.find((category) => category.key === key) || { key, label: "其他", icon: "📦" };
  }

  function inferPrimary(name, counts, webs, code) {
    const key = name.toLowerCase();
    const hasWebApp = webs.length > 0 && code.some((file) => ["js", "css"].includes(file.ext));
    if (/(report|报告|调研|教程|guide|analysis)/i.test(key) && counts.document) return "document";
    if (/(picture|绘本|book|gallery|画册|style|风格|images?)/i.test(key) && counts.image) return "image";
    if (hasWebApp) return "web";
    if (counts.video) return "video";
    if (counts.audio) return "audio";
    if (counts.image) return "image";
    if (counts.document) return "document";
    if (counts.code) return "code";
    if (counts.web) return "web";
    if (counts.data) return "data";
    return "other";
  }

  function chooseCover(images) {
    if (!images.length) return null;
    return [...images].sort((a, b) => coverScore(b) - coverScore(a) || b.mtime - a.mtime)[0];
  }

  function coverScore(file) {
    const name = file.name.toLowerCase();
    const depth = file.path.split("/").length - 1;
    let score = depth === 0 ? 100 : Math.max(0, 70 - depth * 18);
    if (/(cover|poster|ref|封面|参考|^00_|^01_|chapter1)/.test(name)) score += 70;
    if (/(final|selected|main|完整)/.test(name)) score += 30;
    if (/(thumb|icon|avatar|small|favicon)/.test(name)) score -= 80;
    return score;
  }

  function chooseMainVideo(videos) {
    if (!videos.length) return null;
    return [...videos].sort((a, b) => mainVideoScore(b) - mainVideoScore(a) || b.size - a.size)[0];
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
    const name = projectName.toLowerCase();
    return [...files].sort((a, b) => mainNamedScore(b, name) - mainNamedScore(a, name))[0];
  }

  function chooseMainDoc(files, projectName) {
    const markdown = files.filter((file) => file.ext === "md");
    return chooseReadme(markdown) || files.sort((a, b) => b.mtime - a.mtime)[0] || null;
  }

  function chooseReadme(files) {
    if (!files.length) return null;
    return [...files].sort((a, b) => readmeScore(b) - readmeScore(a))[0];
  }

  function readmeScore(file) {
    const name = file.name.toLowerCase();
    const depth = file.path.split("/").length - 1;
    let score = 30 - depth * 5;
    if (name === "readme.md") score += 120;
    if (/报告|教程|guide|report|design|README/i.test(file.name)) score += 60;
    if (file.ext === "md") score += 20;
    return score;
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
    const route = parseRoute();
    if (route.type === "project") renderProject(route.path);
    else if (route.type === "file") renderFile(route.path);
    else renderHome();
    els.sidebar.classList.remove("open");
  }

  function renderChrome() {
    const counts = {};
    state.files.forEach((file) => {
      const category = categoryOf(file);
      counts[category] = (counts[category] || 0) + 1;
    });

    const categories = [
      { key: "all", label: "全部", icon: "✦", count: state.files.length },
      ...CATEGORIES.map((category) => ({ ...category, count: counts[category.key] || 0 })),
      { key: "other", label: "其他", icon: "📦", count: counts.other || 0 },
    ];

    els.categoryNav.innerHTML = categories.map((category) => `
      <button class="category-link ${state.category === category.key ? "active" : ""}" data-category="${category.key}">
        <span>${category.icon}</span><span>${category.label}</span><em>${category.count}</em>
      </button>
    `).join("");

    const activeProject = activeProjectPath();
    els.projectNav.innerHTML = state.projects.map((project) => `
      <a class="project-link ${activeProject === project.path ? "active" : ""}" href="#/project/${encodeURIComponent(project.path)}" title="${escapeAttr(project.path)}">
        <span>${categoryMeta(project.primary).icon}</span>
        <span>${escapeHtml(project.name)}</span>
      </a>
    `).join("");
  }

  function renderHome() {
    const query = state.query;
    const category = state.category;
    let projects = state.projects;
    let files = state.files;

    if (category !== "all") {
      projects = projects.filter((project) => project.counts[category]);
      files = files.filter((file) => categoryOf(file) === category);
    }
    if (query) {
      projects = projects.filter((project) =>
        project.name.toLowerCase().includes(query) ||
        project.path.toLowerCase().includes(query) ||
        project.tags.some((tag) => tag.includes(query))
      );
      files = files.filter((file) =>
        file.name.toLowerCase().includes(query) ||
        file.path.toLowerCase().includes(query) ||
        file.ext.toLowerCase().includes(query)
      );
    }

    const totalSize = state.files.reduce((sum, file) => sum + file.size, 0);
    const stats = [
      ["项目", state.projects.length, "✦"],
      ["文件", state.files.length, "📁"],
      ["视频", categoryCount("video"), "🎬"],
      ["图片", categoryCount("image"), "🖼️"],
      ["音频", categoryCount("audio"), "🎵"],
      ["占用", formatBytes(totalSize), "💾"],
    ];

    els.breadcrumbs.innerHTML = `<a href="#/">Outputs</a><span>›</span><span>${category === "all" ? "全部作品" : categoryMeta(category).label}</span>`;
    els.content.innerHTML = `
      <section class="hero">
        <p class="eyebrow">Offline Creative Library</p>
        <h1>一个页面浏览全部生成结果</h1>
        <p>视频、图片、音频、绘本、技术报告、网页和代码脚本会自动识别与分类。服务每次刷新都实时扫描 outputs，目录里新增文件后无需重新生成 HTML。</p>
        <div class="stat-grid">
          ${stats.map(([label, value, icon]) => `
            <div class="stat-card">
              <strong>${icon} ${value}</strong>
              <span>${label}</span>
            </div>
          `).join("")}
        </div>
      </section>

      <section class="section">
        <div class="chip-row">
          ${categoryChip("all", "全部类型")}
          ${CATEGORIES.map((item) => categoryChip(item.key, `${item.icon} ${item.label}`)).join("")}
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <div>
            <h2>${query ? "搜索结果" : "精选项目"}</h2>
            <p>${projects.length} 个项目匹配当前条件</p>
          </div>
        </div>
        ${projects.length ? `<div class="project-grid">${projects.map(renderProjectCard).join("")}</div>` : emptyBlock("没有匹配的项目")}
      </section>

      <section class="section">
        <div class="section-head">
          <div>
            <h2>${query ? "匹配文件" : "最近更新"}</h2>
            <p>点击文件可直接预览、播放或阅读</p>
          </div>
        </div>
        ${files.length ? `<div class="file-grid">${renderFileCards(query ? files.slice(0, 60) : recentFiles(files, 18))}</div>` : emptyBlock("没有匹配的文件")}
      </section>
    `;
  }

  function categoryChip(key, label) {
    return `<button class="chip ${state.category === key ? "active" : ""}" data-category="${key}">${label}</button>`;
  }

  function categoryCount(key) {
    return state.files.filter((file) => categoryOf(file) === key).length;
  }

  function recentFiles(files, limit) {
    return [...files].sort((a, b) => b.mtime - a.mtime).slice(0, limit);
  }

  function renderProjectCard(project) {
    const meta = categoryMeta(project.primary);
    const summary = projectTags(project).slice(0, 4).map((tag) => `${tag.count} ${tag.label}`).join(" · ");
    const cover = project.cover
      ? `<img loading="lazy" src="${rawUrl(project.cover.path)}" alt="${escapeAttr(project.cover.name)}">`
      : `<div class="cover-icon">${meta.icon}</div>`;
    return `
      <a class="project-card" href="#/project/${encodeURIComponent(project.path)}">
        <div class="cover">
          ${cover}
          <span class="cover-badge">${meta.icon} ${meta.label}</span>
        </div>
        <div class="project-body">
          <h3>${escapeHtml(project.name)}</h3>
          <p>${escapeHtml(summary || "打开项目查看文件")} · 更新于 ${formatDate(project.mtime)}</p>
          <div class="tag-row">
            ${project.tags.slice(0, 5).map((tag) => `<span class="tag ${tag}">${categoryMeta(tag).label}</span>`).join("")}
          </div>
        </div>
      </a>
    `;
  }

  function projectTags(project) {
    return CATEGORIES.filter((category) => project.counts[category.key]).map((category) => ({
      key: category.key,
      label: category.label,
      count: project.counts[category.key],
    }));
  }

  function renderFileCards(files) {
    return files.map((file) => {
      const category = categoryOf(file);
      let thumb = `<div class="file-icon">${categoryMeta(category).icon}</div>`;
      if (category === "image") {
        thumb = `<img loading="lazy" src="${rawUrl(file.path)}" alt="${escapeAttr(file.name)}">`;
      } else if (category === "video") {
        thumb = `<div class="file-icon">🎬</div><span class="cover-badge">${formatBytes(file.size)}</span>`;
      }
      return `
        <a class="file-card" href="#/file/${encodeURIComponent(file.path)}">
          <div class="file-thumb">${thumb}</div>
          <div class="file-meta">
            <strong>${escapeHtml(file.name)}</strong>
            <small>${categoryMeta(category).label} · ${formatDate(file.mtime)}</small>
          </div>
        </a>
      `;
    }).join("");
  }

  function renderProject(path) {
    const project = state.projectByPath.get(path);
    if (!project) {
      els.breadcrumbs.innerHTML = breadcrumbHome("项目不存在");
      els.content.innerHTML = emptyBlock("目录可能已被移动或删除，请刷新后重试。");
      return;
    }

    els.breadcrumbs.innerHTML = `
      <a href="#/">Outputs</a><span>›</span>
      <a href="#/project/${encodeURIComponent(project.path)}">${escapeHtml(project.name)}</a>
    `;

    els.content.innerHTML = `
      <div class="project-layout">
        <section class="panel project-hero">
          <div class="tag-row">
            ${project.tags.map((tag) => `<span class="tag ${tag}">${categoryMeta(tag).icon} ${categoryMeta(tag).label} ${project.counts[tag]}</span>`).join("")}
          </div>
          <h1>${categoryMeta(project.primary).icon} ${escapeHtml(project.name)}</h1>
          <p>${escapeHtml(buildProjectDescription(project))}</p>
          <div class="hero-actions">
            ${project.mainWeb ? `<a class="primary-btn" href="${rawUrl(project.mainWeb.path)}" target="_blank" rel="noreferrer">🌐 打开网页</a>` : ""}
            ${project.mainVideo ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(project.mainVideo.path)}">🎬 播放主视频</a>` : ""}
            ${project.readme ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(project.readme.path)}">📄 阅读文档</a>` : ""}
          </div>
          <div class="featured">${renderFeatured(project)}</div>
          <div class="subsection" data-readme-wrap></div>
          <div class="subsection" data-code-wrap></div>
          ${renderProjectMediaSection(project, "image", "图片精选", project.images.slice(0, 18))}
          ${renderProjectMediaSection(project, "video", "视频片段", project.videos.slice(0, 12))}
          ${renderProjectMediaSection(project, "audio", "音频", project.audios.slice(0, 12))}
          ${renderProjectFileSection(project, "document", "文档")}
          ${renderProjectFileSection(project, "code", "代码脚本")}
          ${renderProjectFileSection(project, "data", "数据文件")}
        </section>
        <aside class="panel tree-panel">
          <h2>文件结构</h2>
          ${renderTree(project.node, project.path, "")}
        </aside>
      </div>
    `;
    hydrateProject(project);
  }

  function renderFeatured(project) {
    if (project.primary === "web" && project.mainWeb) {
      return `<iframe src="${rawUrl(project.mainWeb.path)}" sandbox="allow-scripts allow-forms allow-popups allow-same-origin" loading="lazy" title="${escapeAttr(project.mainWeb.name)}"></iframe>`;
    }
    if (project.mainVideo) {
      return `<video controls preload="metadata" src="${rawUrl(project.mainVideo.path)}#t=0.1"></video>`;
    }
    if (project.mainAudio) {
      return `<audio controls preload="metadata" src="${rawUrl(project.mainAudio.path)}"></audio>`;
    }
    if (project.cover) {
      return `<img data-lightbox="${escapeAttr(project.cover.path)}" src="${rawUrl(project.cover.path)}" alt="${escapeAttr(project.cover.name)}">`;
    }
    return `<div class="featured-placeholder"><div><span>${categoryMeta(project.primary).icon}</span><p>该项目暂无可预览的媒体</p></div></div>`;
  }

  function renderProjectMediaSection(project, category, title, files) {
    if (!files.length) return "";
    if (category === "image") {
      return `
        <div class="subsection">
          <h2>${title} <small>(${project.images.length})</small></h2>
          <div class="mini-grid">
            ${files.map((file) => `
              <a class="mini-thumb" title="${escapeAttr(file.name)}" href="#/file/${encodeURIComponent(file.path)}">
                <img loading="lazy" src="${rawUrl(file.path)}" alt="${escapeAttr(file.name)}">
              </a>
            `).join("")}
          </div>
        </div>
      `;
    }
    return `
      <div class="subsection">
        <h2>${title} <small>(${files.length})</small></h2>
        <div class="file-grid">${renderFileCards(files)}</div>
      </div>
    `;
  }

  function renderProjectFileSection(project, category, title) {
    const files = project.files.filter((file) => categoryOf(file) === category).slice(0, 12);
    if (!files.length) return "";
    return `
      <div class="subsection">
        <h2>${title}</h2>
        <div class="file-grid">${renderFileCards(files)}</div>
      </div>
    `;
  }

  async function hydrateProject(project) {
    if (project.readme) {
      const wrap = document.querySelector("[data-readme-wrap]");
      if (wrap) {
        const text = await fetchText(project.readme.path);
        if (text) {
          wrap.innerHTML = `<h2>项目说明</h2><div class="panel markdown">${renderMarkdown(text, project.readme.path)}</div>`;
        }
      }
    }

    const codeWrap = document.querySelector("[data-code-wrap]");
    if (codeWrap) {
      const selected = project.code
        .filter((file) => (file.path.split("/").length - 1) <= 2)
        .sort((a, b) => b.mtime - a.mtime)
        .slice(0, 3);
      if (!selected.length) return;
      codeWrap.innerHTML = `<h2>代码功能说明</h2><div class="file-grid">${selected.map((file) => `
        <a class="file-card" href="#/file/${encodeURIComponent(file.path)}">
          <div class="file-thumb"><div class="file-icon">${codeIcon(file)}</div></div>
          <div class="file-meta">
            <strong>${escapeHtml(file.name)}</strong>
            <small data-code-summary="${escapeAttr(file.path)}">正在解析代码功能…</small>
          </div>
        </a>
      `).join("")}</div>`;
      for (const file of selected) {
        const target = document.querySelector(`[data-code-summary="${CSS.escape(file.path)}"]`);
        if (!target) continue;
        const text = await fetchText(file.path);
        const summary = text ? summarizeCode(text, file.ext) : null;
        target.textContent = summary && summary.description ? summary.description : `${categoryMeta("code").label} · ${formatBytes(file.size)}`;
      }
    }
  }

  function renderFile(path) {
    const file = state.fileByPath.get(path);
    if (!file) {
      els.breadcrumbs.innerHTML = breadcrumbHome("文件不存在");
      els.content.innerHTML = emptyBlock("文件可能已被移动或删除，请刷新后重试。");
      return;
    }

    const project = projectForFile(file);
    const category = categoryOf(file);
    const siblings = project.files.filter((item) => categoryOf(item) === category);
    const index = siblings.findIndex((item) => item.path === file.path);
    const prev = index > 0 ? siblings[index - 1] : null;
    const next = index >= 0 && index < siblings.length - 1 ? siblings[index + 1] : null;

    els.breadcrumbs.innerHTML = `
      <a href="#/">Outputs</a><span>›</span>
      ${project ? `<a href="#/project/${encodeURIComponent(project.path)}">${escapeHtml(project.name)}</a><span>›</span>` : ""}
      <span>${escapeHtml(file.name)}</span>
    `;

    els.content.innerHTML = `
      <div class="viewer">
        <section class="panel viewer-main">
          <header class="viewer-header">
            <div>
              <h1>${categoryMeta(category).icon} ${escapeHtml(file.name)}</h1>
              <small>${escapeHtml(file.path)} · ${formatBytes(file.size)} · ${formatDate(file.mtime)}</small>
            </div>
            <a class="ghost-btn" href="${rawUrl(file.path)}" target="_blank" rel="noreferrer">新窗口打开</a>
          </header>
          <div class="viewer-stage" id="viewerStage">${renderStagePlaceholder(file)}</div>
          <div class="viewer-toolbar">
            ${prev ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(prev.path)}">‹ 上一个${categoryMeta(category).label}</a>` : `<button class="ghost-btn" disabled>‹ 上一个</button>`}
            <a class="ghost-btn" href="${rawUrl(file.path)}" download="${escapeAttr(file.name)}">下载</a>
            ${next ? `<a class="ghost-btn" href="#/file/${encodeURIComponent(next.path)}">下一个${categoryMeta(category).label} ›</a>` : `<button class="ghost-btn" disabled>下一个 ›</button>`}
          </div>
        </section>
        <aside class="panel tree-panel">
          ${["image", "video", "audio"].includes(category) ? `
            <h2>${categoryMeta(category).label}列表</h2>
            <div class="playlist">
              ${siblings.slice(0, 80).map((item) => `
                <a class="playlist-item ${item.path === file.path ? "active" : ""}" href="#/file/${encodeURIComponent(item.path)}">
                  <span>${categoryMeta(category).icon}</span><span>${escapeHtml(item.name)}</span><small>${formatBytes(item.size)}</small>
                </a>
              `).join("")}
            </div>
          ` : ""}
          <h2>${project ? "项目文件" : "文件信息"}</h2>
          ${project ? renderTree(project.node, project.path, file.path) : ""}
        </aside>
      </div>
    `;

    hydrateFile(file, category);
  }

  function renderStagePlaceholder(file) {
    const category = categoryOf(file);
    if (category === "image") {
      return `<img data-lightbox="${escapeAttr(file.path)}" src="${rawUrl(file.path)}" alt="${escapeAttr(file.name)}">`;
    }
    if (category === "video") {
      return `<video controls preload="metadata" src="${rawUrl(file.path)}#t=0.01"></video>`;
    }
    if (category === "audio") {
      return `<audio controls preload="metadata" src="${rawUrl(file.path)}"></audio>`;
    }
    if (category === "web") {
      return `<iframe src="${rawUrl(file.path)}" sandbox="allow-scripts allow-forms allow-popups allow-same-origin" title="${escapeAttr(file.name)}"></iframe>`;
    }
    if (file.ext === "pdf") {
      return `<iframe src="${rawUrl(file.path)}" title="${escapeAttr(file.name)}"></iframe>`;
    }
    if (TEXT_EXTS.has(file.ext)) {
      return `<div class="loading">正在读取文件内容</div>`;
    }
    return `
      <div class="stage-empty">
        <div>
          <span>📦</span>
          <p>暂不支持内嵌预览此格式，请下载或在系统中打开。</p>
          <a class="primary-btn" href="${rawUrl(file.path)}" target="_blank" rel="noreferrer">打开文件</a>
        </div>
      </div>
    `;
  }

  async function hydrateFile(file, category) {
    const stage = document.getElementById("viewerStage");
    if (!stage || !TEXT_EXTS.has(file.ext) || ["web", "pdf"].includes(category)) return;
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
    let notice = "";
    if (file.ext === "json") {
      try {
        displayed = JSON.stringify(JSON.parse(text), null, 2);
      } catch {
        notice = "JSON 解析失败，以下显示原始内容。";
      }
    }

    const lines = displayed.replace(/\n$/, "").split("\n");
    const limited = lines.length > 5000;
    const visibleLines = limited ? lines.slice(0, 5000) : lines;
    const summary = category === "code" ? summarizeCode(text, file.ext) : null;
    stage.className = "viewer-stage";
    stage.innerHTML = `
      ${summary ? `
        <div class="code-summary">
          ${summary.description ? `<p>${escapeHtml(summary.description)}</p>` : ""}
          ${notice ? `<p>${escapeHtml(notice)}</p>` : ""}
          ${summary.definitions.length ? `
            <div class="definition-list">
              ${summary.definitions.slice(0, 28).map((name) => `<span class="definition">${escapeHtml(name)}</span>`).join("")}
            </div>
          ` : ""}
        </div>
      ` : `<div class="code-summary"><p>${escapeHtml(notice || `${file.ext || "unknown"} 文本文件 · ${lines.length} 行`)}</p></div>`}
      <div class="code-wrap">
        <pre class="code-block">${visibleLines.map((line, index) => `
          <span class="code-line">
            <span class="line-number">${index + 1}</span>
            <code class="line-code" data-line>${highlightLine(line, file.ext)}</code>
          </span>`).join("")}
        </pre>
      </div>
      ${limited ? `<div class="code-summary"><p>文件较大，仅预览前 5000 行，请下载查看完整内容。</p></div>` : ""}
    `;
  }

  function renderTree(node, projectPath, activePath) {
    const children = (node.children || []).slice().sort((a, b) => {
      if ((a.type === "directory") !== (b.type === "directory")) return a.type === "directory" ? -1 : 1;
      return a.name.localeCompare(b.name, "zh-Hans-CN", { numeric: true, sensitivity: "base" });
    });
    return `<div class="tree"><ul>${children.map((child) => {
      if (child.type === "directory") {
        const expanded = !activePath || activePath === child.path || activePath.startsWith(child.path + "/");
        return `
          <li class="folder ${expanded ? "" : "collapsed"}">
            <button type="button" data-folder>
              <span>▾</span><span>📁 ${escapeHtml(child.name)}</span>
            </button>
            ${renderTree(child, projectPath, activePath)}
          </li>
        `;
      }
      return `
        <li>
          <a class="tree-file ${activePath === child.path ? "active" : ""}" href="#/file/${encodeURIComponent(child.path)}" title="${escapeAttr(child.path)}">
            <span>${categoryMeta(categoryOf(child)).icon}</span><span>${escapeHtml(child.name)}</span>
          </a>
        </li>
      `;
    }).join("")}</ul></div>`;
  }

  function summarizeCode(text, ext) {
    const clean = (value) => value.replace(/^\s*"""?/s, "").replace(/"""?\s*$/s, "").replace(/^#+\s?/gm, "").replace(/^\/\//gm, "").replace(/^\*+\s?/gm, "").replace(/\s+/g, " ").trim();
    let description = "";
    const docMatch =
      text.match(/^\s*((?:#[^\n]*\n\s*)*)"""(.*?)"""/s) ||
      text.match(/^\s*((?:#[^\n]*\n\s*)*)'''(.*?)'''/s) ||
      text.match(/^\s*\/\*([\s\S]*?)\*\//) ||
      text.match(/^\s*((?:\/\/[^\n]*\n\s*)+)/);
    if (docMatch) description = clean(docMatch[docMatch.length - 1] || docMatch[1] || "");
    if (!description && ext === "py") {
      const comments = text.match(/^\s*(?:#[^\n]*(?:\n|$))+/);
      if (comments) description = clean(comments[0]);
    }

    const patterns = [
      /^[ \t]*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)/gm,
      /^[ \t]*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)/gm,
      /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/gm,
    ];
    const definitions = [];
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(text)) && definitions.length < 40) {
        if (!definitions.includes(match[1])) definitions.push(match[1]);
      }
    }
    return { description: description.slice(0, 260), definitions };
  }

  function highlightLine(line, ext) {
    const isPythonLike = ext === "py" || ext === "sh" || ext === "yaml" || ext === "yml";
    const patterns = [
      /"(?:\\.|[^"\\])*"/,
      /'(?:\\.|[^'\\])*'/,
      /`(?:\\.|[^`\\])*`/,
      /\/\*.*?\*\//,
      /\/\/[^\n]*/,
    ];
    if (isPythonLike) patterns.push(/#[^\n]*/);
    const tokenRegex = new RegExp(patterns.map((pattern) => `(${pattern.source})`).join("|"), "g");
    const keywordSets = {
      py: ["def", "class", "return", "import", "from", "if", "elif", "else", "for", "while", "try", "except", "finally", "with", "as", "async", "await", "lambda", "in", "not", "and", "or", "None", "True", "False", "raise", "yield", "pass", "break", "continue"],
      js: ["function", "class", "return", "import", "export", "from", "if", "else", "for", "while", "try", "catch", "finally", "const", "let", "var", "async", "await", "new", "extends", "super", "this", "null", "undefined", "true", "false"],
      json: ["true", "false", "null"],
      sh: ["if", "then", "else", "fi", "for", "in", "do", "done", "while", "case", "esac", "function", "return", "export"],
    };
    const words = keywordSets[ext] || (ext === "css" ? [] : keywordSets.js);

    const highlightPlain = (value) => {
      let html = escapeHtml(value);
      if (words.length) {
        html = html.replace(new RegExp(`\\b(${words.join("|")})\\b`, "g"), '<span class="token-keyword">$1</span>');
      }
      html = html.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="token-number">$1</span>');
      return html;
    };

    let result = "";
    let lastIndex = 0;
    let match;
    while ((match = tokenRegex.exec(line)) !== null) {
      result += highlightPlain(line.slice(lastIndex, match.index));
      const tokenClass = match[0].startsWith('"') || match[0].startsWith("'") || match[0].startsWith("`")
        ? "token-string"
        : "token-comment";
      result += `<span class="${tokenClass}">${escapeHtml(match[0])}</span>`;
      lastIndex = tokenRegex.lastIndex;
    }
    result += highlightPlain(line.slice(lastIndex));
    return result || " ";
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
      storeBlock(`<pre><code data-lang="${escapeAttr(lang.trim())}">${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`)
    );

    const lines = withoutFences.split("\n");
    const html = [];
    let listType = null;
    let quote = [];
    let paragraph = [];

    const flushParagraph = () => {
      if (paragraph.length) {
        html.push(`<p>${paragraph.map((line) => inlineMarkdown(line, filePath)).join("<br>")}</p>`);
        paragraph = [];
      }
    };
    const flushQuote = () => {
      if (quote.length) {
        html.push(`<blockquote>${quote.map((line) => inlineMarkdown(line, filePath)).join("<br>")}</blockquote>`);
        quote = [];
      }
    };
    const closeList = () => {
      if (listType) {
        html.push(`</${listType}>`);
        listType = null;
      }
    };

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();
      if (!trimmed) {
        flushParagraph();
        flushQuote();
        closeList();
        continue;
      }
      if (trimmed.startsWith("@@MARKDOWN_BLOCK_")) {
        flushParagraph();
        flushQuote();
        closeList();
        html.push(trimmed);
        continue;
      }
      const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        flushQuote();
        closeList();
        const level = heading[1].length;
        const text = heading[2];
        html.push(`<h${level} id="${slugify(text)}">${inlineMarkdown(text, filePath)}</h${level}>`);
        continue;
      }
      if (/^(\*\*\*|---)\s*$/.test(trimmed)) {
        flushParagraph();
        flushQuote();
        closeList();
        html.push("<hr>");
        continue;
      }
      if (trimmed.startsWith(">")) {
        flushParagraph();
        closeList();
        quote.push(trimmed.replace(/^>\s?/, ""));
        continue;
      }
      if (trimmed.includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[index + 1])) {
        flushParagraph();
        flushQuote();
        closeList();
        const headers = splitMarkdownRow(trimmed);
        const rows = [];
        index += 2;
        while (index < lines.length && lines[index].includes("|")) {
          rows.push(splitMarkdownRow(lines[index]));
          index += 1;
        }
        index -= 1;
        html.push(`
          <table>
            <thead><tr>${headers.map((cell) => `<th>${inlineMarkdown(cell, filePath)}</th>`).join("")}</tr></thead>
            <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell, filePath)}</td>`).join("")}</tr>`).join("")}</tbody>
          </table>
        `);
        continue;
      }
      const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
      const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (unordered || ordered) {
        flushParagraph();
        flushQuote();
        const nextType = unordered ? "ul" : "ol";
        if (listType !== nextType) {
          closeList();
          listType = nextType;
          html.push(`<${listType}>`);
        }
        html.push(`<li>${inlineMarkdown((unordered || ordered)[1], filePath)}</li>`);
        continue;
      }
      flushQuote();
      closeList();
      paragraph.push(trimmed);
    }
    flushParagraph();
    flushQuote();
    closeList();

    return html.join("\n").replace(/@@MARKDOWN_BLOCK_(\d+)@@/g, (_match, index) => blocks[Number(index)]);
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
      `<img src="${markdownUrl(href, filePath, true)}" alt="${alt}" loading="lazy">`
    );
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, (_match, label, href) => {
      const url = markdownUrl(href, filePath, false);
      const openElsewhere = /^(https?:|mailto:|\/raw\/)/.test(url);
      return `<a href="${url}" ${openElsewhere ? 'target="_blank" rel="noreferrer"' : ""}>${label}</a>`;
    });
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    text = text.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    text = text.replace(/@@IC_(\d+)@@/g, (_match, index) => codeTokens[Number(index)]);
    return text;
  }

  function markdownUrl(href, filePath, isMedia) {
    if (!href || href.startsWith("javascript:")) return "#";
    if (/^(https?:|mailto:|data:|#)/.test(href)) return href;
    const baseDir = filePath.includes("/") ? filePath.slice(0, filePath.lastIndexOf("/")) : "";
    const resolved = new URL(href, `http://dashboard.local/${baseDir ? `${baseDir}/` : ""}`).pathname.replace(/^\/+/, "");
    if (!isMedia && /\.md(?:#.*)?$/i.test(resolved)) {
      const [path, hash] = resolved.split("#");
      return `#/file/${encodeURIComponent(path)}${hash ? `#${hash}` : ""}`;
    }
    return rawUrl(resolved);
  }

  function projectForFile(file) {
    const top = file.path.includes("/") ? file.path.split("/")[0] : "__root__";
    return state.projectByPath.get(top);
  }

  function handleGlobalClick(event) {
    const categoryButton = event.target.closest("[data-category]");
    if (categoryButton) {
      event.preventDefault();
      state.category = categoryButton.dataset.category;
      if (!isHomeRoute()) location.hash = "#/";
      else render();
      return;
    }

    const folder = event.target.closest("[data-folder]");
    if (folder) {
      event.preventDefault();
      folder.closest(".folder").classList.toggle("collapsed");
      return;
    }

    const lightboxTarget = event.target.closest("[data-lightbox]");
    if (lightboxTarget) {
      event.preventDefault();
      const path = lightboxTarget.dataset.lightbox;
      const project = projectForFile(state.fileByPath.get(path));
      const images = project ? project.images : state.files.filter((file) => categoryOf(file) === "image");
      openLightbox(images, images.findIndex((file) => file.path === path));
    }
  }

  function openLightbox(files, index) {
    if (!files.length || index < 0) return;
    state.lightboxFiles = files;
    state.lightboxIndex = index;
    updateLightbox();
    els.lightbox.hidden = false;
  }

  function closeLightbox() {
    els.lightbox.hidden = true;
  }

  function moveLightbox(direction) {
    state.lightboxIndex = (state.lightboxIndex + direction + state.lightboxFiles.length) % state.lightboxFiles.length;
    updateLightbox();
  }

  function updateLightbox() {
    const file = state.lightboxFiles[state.lightboxIndex];
    els.lightboxImage.src = rawUrl(file.path);
    els.lightboxImage.alt = file.name;
  }

  function parseRoute() {
    const hash = decodeHash(location.hash || "#/");
    if (hash.startsWith("#/file/")) return { type: "file", path: hash.slice("#/file/".length) };
    if (hash.startsWith("#/project/")) return { type: "project", path: hash.slice("#/project/".length) };
    return { type: "home" };
  }

  function decodeHash(hash) {
    try {
      return decodeURIComponent(hash);
    } catch {
      return hash;
    }
  }

  function isHomeRoute() {
    return parseRoute().type === "home";
  }

  function activeProjectPath() {
    const route = parseRoute();
    if (route.type === "project") return route.path;
    if (route.type === "file") {
      const file = state.fileByPath.get(route.path);
      return file ? projectForFile(file)?.path : null;
    }
    return null;
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

  function rawUrl(path) {
    return "/raw/" + path.split("/").map(encodeURIComponent).join("/");
  }

  function buildProjectDescription(project) {
    const parts = projectTags(project).map((tag) => `${tag.count} 个${tag.label}`);
    return `${parts.join("、") || "暂无分类文件"}；目录大小 ${formatBytes(project.size)}，最近更新于 ${formatDate(project.mtime)}。`;
  }

  function codeIcon(file) {
    if (file.ext === "py") return "🐍";
    if (file.ext === "js") return "JS";
    if (file.ext === "css") return "🎨";
    return categoryMeta("code").icon;
  }

  function humanizeName(name) {
    if (name === "__root__") return "根目录散文件";
    return name
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase())
      .trim();
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "-";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
  }

  function formatDate(timestamp) {
    if (!timestamp) return "未知时间";
    return new Date(timestamp * 1000).toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
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
    toast.timer = window.setTimeout(() => {
      els.toast.hidden = true;
    }, 2600);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }
})();
