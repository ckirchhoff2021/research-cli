/* Image Studio 前端：原生 JS 单页应用 */
'use strict';
// ── 版本自检：一旦加载到新版本，自动再重载一次，确保 JS/CSS 全部一致（防止旧标签长期驻留）──
const BUILD = '20261102e';
try {
  if (localStorage.getItem('istudio_build') !== BUILD) {
    localStorage.setItem('istudio_build', BUILD);
    location.replace(location.pathname + '?b=' + BUILD);
  }
} catch {}
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) { let msg = res.statusText; try { msg = (await res.json()).detail || msg; } catch {} throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)); }
  return res.status === 204 ? null : res.json();
}
function toast(msg, type = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + type; t.textContent = msg;
  $('#toastBox').appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 3600);
}

const PRESETS = [
  ['宫崎骏动漫', '吉卜力宫崎骏手绘动漫风格，清新明亮色彩，治愈系'],
  ['皮克斯3D', '皮克斯式3D CG动画电影质感，卡通渲染，柔和光影'],
  ['赛博朋克', '赛博朋克风格，霓虹灯光，雨夜都市，高对比光影'],
  ['古风国韵', '中国古风国韵，水墨笔触，淡雅色调，古典意境'],
  ['油画质感', '古典文艺复兴油画质感，细腻笔触，伦勃朗布光'],
  ['水彩插画', '水彩插画风格，柔和晕染，淡雅通透，纸张纹理'],
  ['日系二次元', '日系二次元动漫，精致赛璐璐上色，清澈大眼睛'],
  ['写实摄影', '专业人像摄影，85mm镜头，自然光，浅景深，真实质感'],
];

const state = {
  view: 'create',
  mode: 'text2image',           // text2image | edit | style
  refs: [],                     // {name,url}
  prompt: '',
  jobs: new Map(),
  lastResult: null,
  gallery: { uploads: [], generated: [], edits: [] },
};

// ── SSE ──────────────────────────────────────────────
function connectSSE() {
  const es = new EventSource('/api/events');
  es.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'hello') { ev.jobs.forEach(j => state.jobs.set(j.id, j)); updatePill(); }
    else if (ev.type === 'job') {
      state.jobs.set(ev.job.id, ev.job); updatePill();
      if (ev.job.status === 'done' && ev.job.kind === 'generate') refreshResult(ev.job.id);
      if (ev.job.status === 'error') toast('任务失败：' + ev.job.error.slice(0, 120), 'err');
    } else if (ev.type === 'log') { renderLogLive(ev); }
  };
}
function updatePill() {
  const busy = [...state.jobs.values()].filter(j => j.status === 'running' || j.status === 'queued');
  const pill = $('#workerPill');
  pill.textContent = busy.length ? `● 生成中 ${busy.length}` : '● 就绪';
  pill.className = 'pill' + (busy.length ? ' busy' : '');
  const btn = state.view === 'create' ? $('.gen-btn') : null;
  if (btn) btn.disabled = busy.length > 0;
}
async function refreshResult(jobId) {
  const j = await api('/api/jobs/' + jobId);
  if (j.result && state.view === 'create') {
    state.lastResult = j.result;
    renderResult();
    loadGallery();
    toast('✅ 图像生成完成', 'ok');
  }
}

// ── 路由 ─────────────────────────────────────────────
document.addEventListener('click', e => {
  const tab = e.target.closest('.tab');
  if (tab) switchView(tab.dataset.view);
});
function switchView(v) {
  state.view = v;
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.view === v));
  ({ create: renderCreate, editor: renderEditor, gallery: renderGallery })[v]();
}

// ── 视图 1：AI 创作 ──────────────────────────────────
function renderCreate() {
  $('#view').innerHTML = `
  <div class="create-wrap">
    <section class="panel">
      <h3>✨ 创作模式</h3>
      <div class="seg" id="modeSeg">
        <button data-mode="text2image">🎨 文生图</button>
        <button data-mode="edit">🖌 图像编辑</button>
        <button data-mode="style">🌊 风格迁移</button>
      </div>

      <label class="field"><span>参考图（编辑/风格迁移必传，文生图可选用于融合）</span></label>
      <div class="dropzone" id="dz">📤 点击或拖拽图片到这里上传<br><small>支持 JPG / PNG / WebP，≤20MB，可多张</small></div>
      <input type="file" id="fileInput" accept="image/*" multiple hidden />
      <div class="ref-thumbs" id="refThumbs"></div>

      <label class="field"><span id="promptLabel">描述你想要的画面</span>
        <textarea id="promptInput" rows="5" placeholder="例如：雨夜小巷里的古风书生，手提灯笼，暖黄灯光，电影感…"></textarea>
      </label>
      <div class="chips" id="presetChips">
        ${PRESETS.map(([n]) => `<button class="chip" data-preset="${esc(n)}">${esc(n)}</button>`).join('')}
      </div>

      <div class="row2" style="margin-top:14px">
        <label class="field" style="margin:0"><span>输出尺寸</span>
          <select id="sizeSel"><option>2K</option><option>3K</option><option>4K</option></select>
        </label>
        <label class="field" style="margin:0"><span>&nbsp;</span>
          <button class="btn primary gen-btn" style="width:100%">🚀 生成</button>
        </label>
      </div>
      <p class="hint-line" style="margin-top:12px">💡 生成后可在右侧点「🔄 重新生成」附带文字反馈，或直接进编辑器做局部调整。</p>
    </section>

    <section class="result-panel">
      <div class="stage-refs" id="stageRefs" hidden></div>
      <div class="stage" id="stage">
        <div class="placeholder"><span class="big">🖼️</span>生成结果将在这里展示<br><small>支持预览、下载、送去编辑、按反馈重新生成</small></div>
      </div>
      <div class="result-actions" id="resultActions"></div>
      <div class="recent panel"><h3>🕘 最近生成</h3><div class="filmstrip" id="filmstrip"><span class="muted">暂无记录</span></div></div>
    </section>
  </div>`;

  // 模式
  $('#modeSeg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    state.mode = b.dataset.mode;
    $$('#modeSeg button').forEach(x => x.classList.toggle('active', x === b));
    const labels = { text2image: '描述你想要的画面', edit: '描述要如何编辑这张图', style: '描述目标风格' };
    $('#promptLabel').textContent = labels[state.mode];
  });
  $$('#modeSeg button').forEach(b => b.classList.toggle('active', b.dataset.mode === state.mode));

  // 上传
  const dz = $('#dz'), fi = $('#fileInput');
  dz.onclick = () => fi.click();
  fi.onchange = () => uploadFiles(fi.files);
  ['dragover', 'dragenter'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', e => uploadFiles(e.dataTransfer.files));

  // 预设
  $('#presetChips').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    const p = PRESETS.find(x => x[0] === c.dataset.preset)[1];
    const ta = $('#promptInput');
    ta.value = ta.value ? ta.value.trim() + '。' + p : p;
  });

  $('.gen-btn').onclick = () => submitGenerate();
  renderRefs();
  renderResult();
  loadGallery().then(renderFilmstrip);
}

async function uploadFiles(files) {
  for (const f of files) {
    if (!f.type.startsWith('image/')) continue;
    const fd = new FormData(); fd.append('file', f);
    try {
      const r = await api('/api/upload', { method: 'POST', body: fd });
      if (!state.refs.some(x => x.name === r.name)) state.refs.push(r);
      toast('已上传：' + f.name, 'ok');
    } catch (e) { toast('上传失败：' + e.message, 'err'); }
  }
  if (state.view === 'create') renderRefs();
}
function renderRefs() {
  const box = $('#refThumbs'); if (!box) return;
  box.innerHTML = state.refs.map((r, i) => `
    <div class="ref-thumb"><img src="${r.url}" alt="">
      <span class="tag">参考${i + 1}</span>
      <button class="rm" data-i="${i}">✕</button></div>`).join('');
  box.onclick = e => {
    const b = e.target.closest('.rm'); if (!b) return;
    state.refs.splice(+b.dataset.i, 1); renderRefs();
  };
  renderStageRefs();
}
// 右侧展示窗口顶部的「当前参考图」小条：新上传/删除都实时刷新
function renderStageRefs() {
  const box = $('#stageRefs'); if (!box) return;
  if (!state.refs.length) { box.hidden = true; box.innerHTML = ''; return; }
  box.hidden = false;
  box.innerHTML = `<span class="slabel">参考图 ${state.refs.length} 张</span>` +
    state.refs.map((r, i) => `
    <div class="sref" title="${esc(r.name)}"><img src="${r.url}" alt="">
      <span class="n">#${i + 1}</span>
      <button class="x" data-i="${i}">✕</button></div>`).join('');
  box.onclick = e => {
    const b = e.target.closest('.x'); if (!b) return;
    state.refs.splice(+b.dataset.i, 1); renderRefs();
  };
}

async function submitGenerate(feedback = '') {
  const prompt = $('#promptInput') ? $('#promptInput').value.trim() : state.prompt;
  state.prompt = prompt;
  if (!prompt) return toast('请先输入提示词', 'err');
  if (state.mode !== 'text2image' && state.refs.length === 0)
    return toast(state.mode === 'style' ? '风格迁移需要先上传参考图' : '图像编辑需要先上传参考图', 'err');
  const busy = [...state.jobs.values()].some(j => j.status === 'running' || j.status === 'queued');
  if (busy) return toast('请等待当前任务完成', 'err');
  const size = $('#sizeSel').value;
  setStageBusy(feedback ? '按反馈重新生成中…' : '生成中…');
  try {
    await api('/api/jobs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: 'generate', options: {
        prompt, mode: state.mode, size, feedback, images: state.refs.map(r => r.name),
      }}),
    });
  } catch (e) {
    setStageError(e.message);
    toast(e.message, 'err');
  }
}
function setStageBusy(txt) {
  $('#stage').innerHTML = `<div class="placeholder"><div class="spinner"></div>${txt}<br><small>通常需要 10–40 秒，可点右上角 📜 看实时日志</small></div>`;
  $('#resultActions').innerHTML = '';
}
function setStageError(msg) {
  $('#stage').innerHTML = `<div class="placeholder" style="color:var(--err)"><span class="big">⚠️</span>生成失败<br><small style="max-width:420px;display:inline-block;margin-top:8px">${esc(msg)}</small></div>`;
}
function renderResult() {
  const r = state.lastResult;
  const stage = $('#stage');
  if (!r) return;
  stage.innerHTML = `<img src="${r.url}?t=${Date.now()}" alt="result">`;
  $('#resultActions').innerHTML = `
    <button class="btn primary" id="btnRegen">🔄 重新生成（可带反馈）</button>
    <a class="btn" href="${r.url}" download><span>⬇️ 下载</span></a>
    <button class="btn" id="btnEdit">🖌 送去编辑</button>
    <button class="btn ghost-btn" id="btnRef">➕ 用作参考图</button>`;
  $('#btnRegen').onclick = askFeedback;
  $('#btnEdit').onclick = () => loadEditor(r.url, r.name);
  $('#btnRef').onclick = () => {
    if (!state.refs.some(x => x.name === r.name)) state.refs.push(r);
    renderRefs(); toast('已加入参考图');
  };
}
async function renderFilmstrip() {
  const box = $('#filmstrip'); if (!box) return;
  const items = state.gallery.generated.slice(0, 12);
  if (!items.length) { box.innerHTML = '<span class="muted">暂无记录</span>'; return; }
  box.innerHTML = items.map(it => `
    <div class="cell" data-name="${esc(it.name)}" data-url="/media/generated/${encodeURIComponent(it.name)}">
      <img src="/media/generated/${encodeURIComponent(it.name)}" loading="lazy">
      <span class="m-tag">${it.name.split('_')[0]}</span>
    </div>`).join('');
  box.onclick = e => {
    const cell = e.target.closest('.cell'); if (!cell) return;
    state.lastResult = { name: cell.dataset.name, url: cell.dataset.url };
    renderResult();
  };
}
async function loadGallery() {
  state.gallery = await api('/api/gallery');
  return state.gallery;
}

// ── 反馈弹窗 ─────────────────────────────────────────
function askFeedback() {
  const m = $('#feedbackModal');
  $('#fbTitle').textContent = '🔄 带反馈重新生成';
  $('#fbHint').textContent = '描述你希望调整的地方，AI 会在原提示词基础上修改；留空则原样再来一次。';
  $('#fbText').value = '';
  m.hidden = false;
  setTimeout(() => $('#fbText').focus(), 50);
  const close = () => { m.hidden = true; };
  $('#fbClose').onclick = close; $('#fbCancel').onclick = close;
  $('#fbSubmit').onclick = async () => {
    const fb = $('#fbText').value.trim(); close();
    await submitGenerate(fb);
  };
}

// ── 视图 2：图像编辑器（本地 Photoshop 能力） ─────────
const Ed = {
  img: null, history: [], future: [],
  adj: { bri: 100, con: 100, sat: 100, hue: 0, blur: 0, gray: 0, sep: 0 },
  tool: 'move', brushColor: '#ff3b30', brushSize: 24, crop: null, inpaint: null,
};

function renderEditor() {
  $('#view').innerHTML = `
  <div class="editor-wrap">
    <aside class="tool-col">
      <div class="tool-group">
        <div class="gt">打开图片</div>
        <button class="btn sm" id="loadBtn" style="width:100%">📂 从本地上传</button>
        <input type="file" id="editorFile" accept="image/*" hidden>
      </div>
      <div class="tool-group">
        <div class="gt">历史</div>
        <div class="tool-grid">
          <button class="btn" id="undoBtn">↩️ 撤销</button>
          <button class="btn" id="redoBtn">↪️ 重做</button>
        </div>
        <button class="btn sm" id="resetBtn" style="width:100%;margin-top:8px">🧹 恢复原图</button>
      </div>
      <div class="tool-group">
        <div class="gt">变换</div>
        <div class="tool-grid">
          <button class="btn" id="rotL">⟲ 左转90°</button>
          <button class="btn" id="rotR">⟳ 右转90°</button>
          <button class="btn" id="flipH">↔ 水平翻转</button>
          <button class="btn" id="flipV">↕ 垂直翻转</button>
        </div>
      </div>
      <div class="tool-group">
        <div class="gt">裁剪</div>
        <button class="btn" id="cropBtn" style="width:100%">▢ 进入裁剪</button>
        <div class="tool-grid" id="cropActions" style="margin-top:8px;display:none">
          <button class="btn primary" id="cropApply">✓ 应用</button>
          <button class="btn ghost-btn" id="cropCancel">取消</button>
        </div>
      </div>
      <div class="tool-group">
        <div class="gt">局部绘制</div>
        <div class="tool-grid">
          <button class="btn" id="brushBtn">🖌 画笔</button>
          <button class="btn" id="eraserBtn">🧽 橡皮</button>
          <button class="btn inpaint-tool-btn" id="inpaintBtn">✨ AI 局部重绘</button>
        </div>
        <div class="swatch-row" style="margin-top:10px">
          <input type="color" id="brushColor" value="#ff3b30">
          <span class="muted" style="font-size:12px">颜色 / 粗细</span>
        </div>
        <input type="range" id="brushSize" min="2" max="120" value="24" style="margin-top:8px">
        <div id="inpaintActions" hidden style="margin-top:10px">
          <button class="btn primary sm" id="ipConfirm" style="width:100%">✍ 描述要重绘的内容</button>
          <button class="btn ghost-btn sm" id="ipCancel" style="width:100%;margin-top:6px">取消框选</button>
          <p class="muted" style="font-size:11px;margin-top:6px;line-height:1.5">💡 在图上按住拖动能重新框选；虚线框可拖动、四角可缩放</p>
        </div>
      </div>
    </aside>

    <div class="canvas-zone" id="canvasZone">
      <div class="canvas-empty" id="canvasEmpty"><span class="big">🖌️</span>从本地上传，或在图库/结果里点「送去编辑」</div>
      <canvas id="editCanvas"></canvas>
      <div id="cropOverlay">
        <div class="crop-handle tl" data-h="tl"></div><div class="crop-handle tr" data-h="tr"></div>
        <div class="crop-handle bl" data-h="bl"></div><div class="crop-handle br" data-h="br"></div>
      </div>
      <div id="inpaintOverlay">
        <span class="ip-tag">✨ AI 重绘区域</span>
        <div class="crop-handle tl" data-h="tl"></div><div class="crop-handle tr" data-h="tr"></div>
        <div class="crop-handle bl" data-h="bl"></div><div class="crop-handle br" data-h="br"></div>
      </div>
      <div class="canvas-busy" id="canvasBusy" hidden>
        <div class="spinner"></div><span id="canvasBusyTxt">处理中…</span>
      </div>
    </div>

    <aside class="adjust-col">
      <div class="tool-group">
        <div class="gt">调整（实时预览）</div>
        ${adjTpl('bri','亮度',0,200,'%')}
        ${adjTpl('con','对比度',0,200,'%')}
        ${adjTpl('sat','饱和度',0,200,'%')}
        ${adjTpl('hue','色相',0,360,'°')}
        ${adjTpl('blur','模糊',0,10,'px')}
        ${adjTpl('gray','黑白',0,100,'%')}
        ${adjTpl('sep','复古',0,100,'%')}
        <button class="btn primary sm" id="applyAdj" style="width:100%;margin-top:6px">✓ 应用调整到画面</button>
      </div>
      <div class="tool-group">
        <div class="gt">导出</div>
        <button class="btn accent" id="saveCopy">💾 保存副本到图库</button>
        <button class="btn" id="dlBtn">⬇️ 下载图片</button>
        <button class="btn ghost-btn" id="toAIBtn">✨ 送 AI 继续编辑</button>
      </div>
    </aside>
  </div>`;

  $('#loadBtn').onclick = () => $('#editorFile').click();
  $('#editorFile').onchange = e => {
    const f = e.target.files[0]; if (!f) return;
    const rd = new FileReader();
    rd.onload = () => loadEditorImage(rd.result);
    rd.readAsDataURL(f);
  };
  $('#undoBtn').onclick = undo; $('#redoBtn').onclick = redo;
  $('#resetBtn').onclick = resetAll;
  $('#rotL').onclick = () => transform('rotL');
  $('#rotR').onclick = () => transform('rotR');
  $('#flipH').onclick = () => transform('flipH');
  $('#flipV').onclick = () => transform('flipV');
  $('#cropBtn').onclick = enterCrop;
  $('#cropApply').onclick = applyCrop;
  $('#cropCancel').onclick = cancelCrop;
  $('#brushBtn').onclick = () => setTool('brush');
  $('#eraserBtn').onclick = () => setTool('eraser');
  $('#brushColor').oninput = e => Ed.brushColor = e.target.value;
  $('#brushSize').oninput = e => Ed.brushSize = +e.target.value;
  $('#inpaintBtn').onclick = enterInpaint;
  $('#ipCancel').onclick = exitInpaint;
  $('#ipConfirm').onclick = openInpaintModal;
  $$('input[data-adj]').forEach(el => el.addEventListener('input', () => {
    Ed.adj[el.dataset.adj] = +el.value;
    $(`#v_${el.dataset.adj}`).textContent = el.value + el.dataset.unit;
    renderCanvas(true);
  }));
  $$('input[data-adj]').forEach(el => {
    el.value = Ed.adj[el.dataset.adj];
    $(`#v_${el.dataset.adj}`).textContent = el.value + el.dataset.unit;
  });
  $('#applyAdj').onclick = commitAdjustments;
  $('#saveCopy').onclick = saveCopy;
  $('#dlBtn').onclick = downloadCanvas;
  $('#toAIBtn').onclick = sendToAI;
  bindDrawing();
  updateUndoBtns();
  if (Ed.img) {
    $('#canvasEmpty').style.display = 'none';
    const adjDirty = JSON.stringify(Ed.adj) !== JSON.stringify({ bri:100,con:100,sat:100,hue:0,blur:0,gray:0,sep:0 });
    renderCanvas(adjDirty);
  }
}
function adjTpl(key, label, min, max, unit) {
  const val = Ed.adj[key];
  return `<div class="adj"><div class="al"><span>${label}</span><b id="v_${key}">${val}${unit}</b></div>
    <input type="range" data-adj="${key}" data-unit="${unit}" min="${min}" max="${max}" value="${val}"></div>`;
}

function loadEditor(url, name) {
  switchView('editor');
  setTimeout(() => loadEditorImage(url), 30);
}
function loadEditorImage(src) {
  const img = new Image();
  img.onload = () => {
    Ed.img = img; Ed.history = []; Ed.future = []; resetAdj();
    Ed.tool = 'move';
    if (state.view === 'editor') {
      $('#canvasEmpty').style.display = 'none';
      renderCanvas(false); updateUndoBtns(); syncToolBtns();
    }
    toast('图片已载入编辑器', 'ok');
  };
  img.onerror = () => toast('图片加载失败', 'err');
  img.src = src;
}
function filterStr() {
  const a = Ed.adj;
  return `brightness(${a.bri}%) contrast(${a.con}%) saturate(${a.sat}%) hue-rotate(${a.hue}deg) blur(${a.blur}px) grayscale(${a.gray}%) sepia(${a.sep}%)`;
}
function renderCanvas(useFilter = true) {
  const cv = $('#editCanvas'); if (!cv || !Ed.img) return;
  cv.width = Ed.img.naturalWidth; cv.height = Ed.img.naturalHeight;
  const ctx = cv.getContext('2d');
  ctx.filter = useFilter ? filterStr() : 'none';
  ctx.drawImage(Ed.img, 0, 0);
}
function pushHistory() {
  if (!Ed.img) return;
  Ed.history.push(Ed.img.src);
  if (Ed.history.length > 15) Ed.history.shift();
}
function snapshotBase() {
  // 把当前（含滤镜）画面固化为新 base
  const url = $('#editCanvas').toDataURL('image/png');
  return new Promise(res => {
    const im = new Image();
    im.onload = () => res(im);
    im.src = url;
  });
}
function resetAdj() {
  Ed.adj = { bri: 100, con: 100, sat: 100, hue: 0, blur: 0, gray: 0, sep: 0 };
  if (state.view !== 'editor') return;
  $$('input[data-adj]').forEach(el => {
    el.value = Ed.adj[el.dataset.adj];
    $(`#v_${el.dataset.adj}`).textContent = el.value + el.dataset.unit;
  });
}
async function commitAdjustments() {
  if (!Ed.img) return;
  pushHistory();
  Ed.img = await snapshotBase();
  resetAdj(); renderCanvas(false); updateUndoBtns();
  toast('调整已应用', 'ok');
}
function undo() {
  if (!Ed.history.length) return;
  Ed.future.push(Ed.img.src);
  const src = Ed.history.pop();
  Ed.img = new Image(); Ed.img.onload = () => { resetAdj(); renderCanvas(false); updateUndoBtns(); };
  Ed.img.src = src;
}
function redo() {
  if (!Ed.future.length) return;
  Ed.history.push(Ed.img.src);
  const src = Ed.future.pop();
  Ed.img = new Image(); Ed.img.onload = () => { resetAdj(); renderCanvas(false); updateUndoBtns(); };
  Ed.img.src = src;
}
function updateUndoBtns() {
  if (state.view !== 'editor') return;
  $('#undoBtn').disabled = !Ed.history.length;
  $('#redoBtn').disabled = !Ed.future.length;
}
function resetAll() {
  if (!Ed.img || !Ed.history.length) return;
  pushHistory(); Ed.future = [];
  const first = Ed.history.shift();
  Ed.history = [];
  Ed.img = new Image(); Ed.img.onload = () => { resetAdj(); renderCanvas(false); updateUndoBtns(); };
  Ed.img.src = first;
}

async function transform(kind) {
  if (!Ed.img) return;
  pushHistory();
  // 先固化当前滤镜
  Ed.img = await snapshotBase(); resetAdj();
  const w = Ed.img.naturalWidth, h = Ed.img.naturalHeight;
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d');
  if (kind === 'rotL' || kind === 'rotR') { c.width = h; c.height = w; } else { c.width = w; c.height = h; }
  ctx.translate(c.width / 2, c.height / 2);
  if (kind === 'rotL') ctx.rotate(-Math.PI / 2);
  if (kind === 'rotR') ctx.rotate(Math.PI / 2);
  if (kind === 'flipH') ctx.scale(-1, 1);
  if (kind === 'flipV') ctx.scale(1, -1);
  ctx.drawImage(Ed.img, -w / 2, -h / 2);
  Ed.img = await new Promise(res => { const im = new Image(); im.onload = () => res(im); im.src = c.toDataURL('image/png'); });
  renderCanvas(false); updateUndoBtns();
}

// ── 裁剪 ──
function setTool(t) { Ed.tool = Ed.tool === t ? 'move' : t; syncToolBtns(); }
function syncToolBtns() {
  if (state.view !== 'editor') return;
  $('#brushBtn').classList.toggle('on', Ed.tool === 'brush');
  $('#eraserBtn').classList.toggle('on', Ed.tool === 'eraser');
  $('#inpaintBtn').classList.toggle('on', Ed.tool === 'inpaint');
  const cv = $('#editCanvas');
  cv.style.cursor = ['brush', 'eraser', 'inpaint'].includes(Ed.tool) ? 'crosshair' : 'default';
}
function enterCrop() {
  if (!Ed.img) return;
  if (Ed.tool === 'brush' || Ed.tool === 'eraser') setTool('move');
  Ed.tool = 'crop';
  const ov = $('#cropOverlay'), cv = $('#editCanvas');
  $('#cropActions').style.display = 'grid';
  $('#cropBtn').classList.add('on');
  // 初始选区 70% 居中（用相对画布的比例）
  Ed.crop = { x: .15, y: .15, w: .7, h: .7 };
  ov.classList.add('show');
  positionCrop();
}
function positionBox(sel, c) {
  const cv = $('#editCanvas'), ov = $(sel), zone = $('#canvasZone');
  const r = cv.getBoundingClientRect(), z = zone.getBoundingClientRect();
  const bx = r.left - z.left, by = r.top - z.top;
  ov.style.left = (bx + c.x * r.width) + 'px';
  ov.style.top = (by + c.y * r.height) + 'px';
  ov.style.width = (c.w * r.width) + 'px';
  ov.style.height = (c.h * r.height) + 'px';
}
function positionCrop() { if (Ed.crop) positionBox('#cropOverlay', Ed.crop); }
function positionInpaint() { if (Ed.inpaint) positionBox('#inpaintOverlay', Ed.inpaint); }
function cancelCrop() {
  Ed.tool = 'move'; Ed.crop = null;
  $('#cropOverlay').classList.remove('show');
  $('#cropActions').style.display = 'none';
  $('#cropBtn').classList.remove('on');
}

// ── AI 局部重绘 ──
function enterInpaint() {
  if (!Ed.img) return toast('请先打开图片', 'err');
  if (Ed.tool === 'crop') cancelCrop();
  Ed.inpaint = Ed.inpaint || { x: .2, y: .28, w: .6, h: .44 };
  Ed.tool = 'inpaint'; syncToolBtns();
  $('#inpaintActions').hidden = false;
  $('#inpaintOverlay').classList.add('show');
  positionInpaint();
}
function exitInpaint() {
  Ed.inpaint = null;
  if (Ed.tool === 'inpaint') { Ed.tool = 'move'; syncToolBtns(); }
  $('#inpaintActions').hidden = true;
  $('#inpaintOverlay').classList.remove('show');
}
function openInpaintModal() {
  if (!Ed.inpaint) return;
  const m = $('#inpaintModal');
  $('#ipmText').value = '';
  m.hidden = false;
  setTimeout(() => $('#ipmText').focus(), 50);
}
function setCanvasBusy(on, txt) {
  $('#canvasBusy').hidden = !on;
  $('#canvasBusyTxt').textContent = txt || '处理中…';
}
async function waitJobResult(id) {
  for (let i = 0; i < 120; i++) {
    const j = await api('/api/jobs/' + id);
    if (j.status === 'done') return j.result;
    if (j.status === 'error') throw new Error(j.error || '生成失败');
    await new Promise(r => setTimeout(r, 1500));
  }
  throw new Error('生成超时');
}
async function submitInpaint() {
  const box = { ...Ed.inpaint };
  const prompt = $('#ipmText').value.trim();
  $('#inpaintModal').hidden = true;
  // 先把未应用的调色固化进画面，再导出 JPEG
  Ed.img = await snapshotBase(); resetAdj(); renderCanvas(false);
  const dataUrl = $('#editCanvas').toDataURL('image/jpeg', .95);
  pushHistory();
  exitInpaint();
  setCanvasBusy(true, '✨ AI 局部重绘中… 通常 20–40 秒，可点 📜 看日志');
  try {
    const job = await api('/api/inpaint', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: dataUrl, box, prompt }),
    });
    const result = await waitJobResult(job.id);
    Ed.img = await new Promise(res => {
      const im = new Image(); im.onload = () => res(im); im.src = result.url;
    });
    if (state.view === 'editor') { renderCanvas(false); updateUndoBtns(); }
    toast('✨ 局部重绘完成', 'ok');
  } catch (e) {
    toast('局部重绘失败：' + e.message, 'err');
  } finally {
    setCanvasBusy(false);
  }
}
function startInpaintDrag(e) {
  const cv = $('#editCanvas'), r = cv.getBoundingClientRect();
  const clamp01 = v => Math.min(Math.max(v, 0), 1);
  const sx = clamp01((e.clientX - r.left) / r.width);
  const sy = clamp01((e.clientY - r.top) / r.height);
  Ed.inpaint = { x: sx, y: sy, w: 0, h: 0 };
  $('#inpaintOverlay').classList.add('show');
  positionInpaint();
  function onMove(ev) {
    const cx = clamp01((ev.clientX - r.left) / r.width);
    const cy = clamp01((ev.clientY - r.top) / r.height);
    Ed.inpaint = { x: Math.min(sx, cx), y: Math.min(sy, cy),
      w: Math.abs(cx - sx), h: Math.abs(cy - sy) };
    positionInpaint();
  }
  function onUp() {
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
    if (Ed.inpaint.w < .02 || Ed.inpaint.h < .02)
      Ed.inpaint = { x: .2, y: .28, w: .6, h: .44 };
    positionInpaint();
  }
  document.addEventListener('pointermove', onMove);
  document.addEventListener('pointerup', onUp);
}
async function applyCrop() {
  if (!Ed.crop || !Ed.img) return;
  pushHistory();
  Ed.img = await snapshotBase(); resetAdj();
  const { x, y, w, h } = Ed.crop;
  const c = document.createElement('canvas');
  c.width = Math.max(2, Math.round(w * Ed.img.naturalWidth));
  c.height = Math.max(2, Math.round(h * Ed.img.naturalHeight));
  c.getContext('2d').drawImage(Ed.img,
    x * Ed.img.naturalWidth, y * Ed.img.naturalHeight, w * Ed.img.naturalWidth, h * Ed.img.naturalHeight, 0, 0, c.width, c.height);
  Ed.img = await new Promise(res => { const im = new Image(); im.onload = () => res(im); im.src = c.toDataURL('image/png'); });
  cancelCrop(); renderCanvas(false); updateUndoBtns();
  toast('裁剪已应用', 'ok');
}
(function bindCropDrag() {
  document.addEventListener('pointerdown', e => {
    if (state.view !== 'editor') return;
    const which = Ed.crop ? { sel: '#cropOverlay', key: 'crop' }
      : Ed.inpaint ? { sel: '#inpaintOverlay', key: 'inpaint' } : null;
    if (!which) return;
    const ov = $(which.sel);
    if (!ov.classList.contains('show')) return;
    const handle = e.target.closest('.crop-handle');
    const mode = handle ? handle.dataset.h
      : (e.target === ov || e.target.classList.contains('ip-tag') ? 'move' : null);
    if (!mode) return;
    e.preventDefault();
    const cv = $('#editCanvas');
    const rect = cv.getBoundingClientRect();
    const start = { x: e.clientX, y: e.clientY, c: { ...Ed[which.key] }, mode };
    function onMove(ev) {
      const dx = (ev.clientX - start.x) / rect.width;
      const dy = (ev.clientY - start.y) / rect.height;
      let { x, y, w, h } = start.c;
      if (mode === 'move') { x += dx; y += dy; }
      if (mode.includes('l')) { x += dx; w -= dx; }
      if (mode.includes('r')) { w += dx; }
      if (mode.includes('t')) { y += dy; h -= dy; }
      if (mode.includes('b')) { h += dy; }
      x = Math.min(Math.max(0, x), 1 - .05); y = Math.min(Math.max(0, y), 1 - .05);
      w = Math.min(Math.max(.05, w), 1 - x); h = Math.min(Math.max(.05, h), 1 - y);
      Ed[which.key] = { x, y, w, h };
      positionBox(which.sel, Ed[which.key]);
    }
    function onUp() {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
    }
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  });
  window.addEventListener('resize', () => {
    if (state.view !== 'editor') return;
    if (Ed.crop) positionCrop();
    if (Ed.inpaint) positionInpaint();
  });
})();

// ── 画笔/橡皮 ──
let drawing = false, lastPt = null;
function bindDrawing() {
  const cv = $('#editCanvas');
  cv.addEventListener('pointerdown', async e => {
    if (Ed.img && Ed.tool === 'inpaint') { startInpaintDrag(e); return; }
    if (!Ed.img || (Ed.tool !== 'brush' && Ed.tool !== 'eraser')) return;
    e.preventDefault();
    // 落笔前固化未应用的调整，并入栈历史
    const adjActive = JSON.stringify(Ed.adj) !== JSON.stringify({ bri:100,con:100,sat:100,hue:0,blur:0,gray:0,sep:0 });
    if (adjActive) { Ed.img = await snapshotBase(); resetAdj(); renderCanvas(false); }
    pushHistory();
    drawing = true; lastPt = ptOnCanvas(e, cv);
    cv.setPointerCapture(e.pointerId);
    drawDot(lastPt);
  });
  cv.addEventListener('pointermove', e => {
    if (!drawing) return;
    e.preventDefault();
    const p = ptOnCanvas(e, cv);
    stroke(lastPt, p); lastPt = p;
  });
  ['pointerup', 'pointercancel'].forEach(ev => cv.addEventListener(ev, () => {
    if (!drawing) return;
    drawing = false;
    const url = cv.toDataURL('image/png');
    Ed.img = new Image(); Ed.img.onload = () => {
      renderCanvas(false); updateUndoBtns();
      const u = $('#undoBtn');
      if (u) { u.classList.remove('pulse'); void u.offsetWidth; u.classList.add('pulse'); }
    };
    Ed.img.src = url;
  }));
}
function ptOnCanvas(e, cv) {
  const r = cv.getBoundingClientRect();
  return {
    x: (e.clientX - r.left) / r.width * cv.width,
    y: (e.clientY - r.top) / r.height * cv.height,
  };
}
function drawCtxSetup() {
  const ctx = $('#editCanvas').getContext('2d');
  ctx.filter = 'none';
  ctx.lineCap = ctx.lineJoin = 'round';
  ctx.lineWidth = Ed.brushSize;
  if (Ed.tool === 'eraser') { ctx.globalCompositeOperation = 'destination-out'; ctx.strokeStyle = 'rgba(0,0,0,1)'; ctx.fillStyle = 'rgba(0,0,0,1)'; }
  else { ctx.globalCompositeOperation = 'source-over'; ctx.strokeStyle = Ed.brushColor; ctx.fillStyle = Ed.brushColor; }
  return ctx;
}
function drawDot(p) {
  const ctx = drawCtxSetup();
  ctx.beginPath(); ctx.arc(p.x, p.y, Ed.brushSize / 2, 0, Math.PI * 2); ctx.fill();
}
function stroke(a, b) {
  const ctx = drawCtxSetup();
  ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
}

// ── 导出 ──
function canvasDataURL() {
  // 导出时带上当前未应用的滤镜
  renderCanvas(true);
  const url = $('#editCanvas').toDataURL('image/png');
  renderCanvas(true);
  return url;
}
async function saveCopy() {
  if (!Ed.img) return toast('请先打开图片', 'err');
  try {
    const r = await api('/api/save-edit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data_url: canvasDataURL() }),
    });
    toast('💾 已保存到图库：' + r.name, 'ok');
    await loadGallery();
    return r;
  } catch (e) { toast('保存失败：' + e.message, 'err'); }
}
function downloadCanvas() {
  if (!Ed.img) return toast('请先打开图片', 'err');
  const a = document.createElement('a');
  a.href = canvasDataURL(); a.download = 'image-studio-' + Date.now() + '.png';
  a.click();
}
async function sendToAI() {
  if (!Ed.img) return toast('请先打开图片', 'err');
  const r = await saveCopy();
  if (!r) return;
  state.refs = [{ name: r.name, url: r.url }];
  state.mode = 'edit';
  switchView('create');
  toast('已送入 AI 创作，写好修改要求后点生成', 'ok');
}

// ── 视图 3：图库 ─────────────────────────────────────
let galTab = 'all';
async function renderGallery() {
  await loadGallery();
  const groups = [
    ['all', '全部'], ['generated', 'AI 生成'], ['uploads', '上传'], ['edits', '我的编辑'],
  ];
  const all = [
    ...state.gallery.generated.map(x => ({ ...x, d: 'generated' })),
    ...state.gallery.uploads.map(x => ({ ...x, d: 'uploads' })),
    ...state.gallery.edits.map(x => ({ ...x, d: 'edits' })),
  ].sort((a, b) => b.mtime - a.mtime);
  const items = galTab === 'all' ? all : all.filter(x => x.d === galTab);
  $('#view').innerHTML = `
  <div class="gallery-wrap">
    <div class="gal-tabs">${groups.map(([k, n]) =>
      `<button class="${galTab === k ? 'active' : ''}" data-tab="${k}">${n}</button>`).join('')}</div>
    ${items.length ? `<div class="gal-grid">${items.map(it => `
      <div class="gal-card">
        <div class="imgbox" data-preview="/media/${it.d}/${encodeURIComponent(it.name)}">
          <img src="/media/${it.d}/${encodeURIComponent(it.name)}?w=400" loading="lazy">
        </div>
        <div class="meta">
          <div class="nm" title="${esc(it.name)}">${esc(it.name)}</div>
          <div class="sub">${it.d} · ${it.size_kb}KB</div>
          <div class="acts">
            <button data-act="edit" data-url="/media/${it.d}/${encodeURIComponent(it.name)}">🖌 编辑</button>
            <button data-act="ref" data-name="${esc(it.name)}" data-url="/media/${it.d}/${encodeURIComponent(it.name)}">➕ 参考</button>
            <button data-act="dl" data-url="/media/${it.d}/${encodeURIComponent(it.name)}">⬇️</button>
          </div>
        </div>
      </div>`).join('')}</div>`
      : `<div class="empty-gal"><span class="big">🗂️</span>这里还没有图片，去 AI 创作页生成一张吧</div>`}
  </div>`;
  $('.gal-tabs').onclick = e => { const b = e.target.closest('button'); if (!b) return; galTab = b.dataset.tab; renderGallery(); };
  $('#view').onclick = e => {
    const pv = e.target.closest('[data-preview]');
    if (pv) return openLightbox(pv.dataset.preview);
    const b = e.target.closest('[data-act]'); if (!b) return;
    const url = b.dataset.url;
    if (b.dataset.act === 'edit') loadEditor(url);
    if (b.dataset.act === 'ref') {
      const r = { name: b.dataset.name, url };
      if (!state.refs.some(x => x.name === r.name)) state.refs.push(r);
      switchView('create'); toast('已加入参考图');
    }
    if (b.dataset.act === 'dl') { const a = document.createElement('a'); a.href = url; a.download = ''; a.click(); }
  };
}

// ── 灯箱 ──
function openLightbox(src) {
  const box = document.createElement('div');
  box.id = 'lightbox'; box.innerHTML = `<img src="${src}">`;
  box.onclick = () => box.remove();
  document.body.appendChild(box);
}

// ── 日志抽屉 ──
let logJobId = null;
$('#logBtn').onclick = () => {
  const d = $('#logDrawer');
  d.hidden = !d.hidden;
  if (!d.hidden) renderLogList();
};
$('#logClose').onclick = () => { $('#logDrawer').hidden = true; };

// AI 局部重绘弹窗
$('#ipmClose').onclick = $('#ipmCancel').onclick = () => { $('#inpaintModal').hidden = true; };
$('#ipmSubmit').onclick = submitInpaint;
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || state.view !== 'editor' || !Ed.inpaint) return;
  if ($('#inpaintModal').hidden) exitInpaint();
});
function renderLogList() {
  const jobs = [...state.jobs.values()].sort((a, b) => b.created_at - a.created_at).slice(0, 8);
  logJobId = jobs[0]?.id || null;
  $('#logBody').textContent = jobs.map(j =>
    `【${j.status}】${j.title}${j.error ? '\n❌ ' + j.error : ''}`).join('\n\n');
  if (logJobId) fillJobLogs(logJobId);
}
async function fillJobLogs(id) {
  try {
    const j = await api('/api/jobs/' + id);
    $('#logBody').textContent = `【${j.status}】${j.title}\n\n` + j.logs.map(l => l.msg).join('\n') +
      (j.error ? '\n\n❌ ' + j.error : '');
  } catch {}
}
function renderLogLive(ev) {
  const d = $('#logDrawer');
  if (d.hidden) return;
  if (state.jobs.size) {
    const latest = [...state.jobs.values()].sort((a, b) => b.created_at - a.created_at)[0];
    if (latest && (latest.status === 'running' || latest.status === 'queued')) fillJobLogs(latest.id);
  }
}

// ── 启动 ──
connectSSE();
renderCreate();
