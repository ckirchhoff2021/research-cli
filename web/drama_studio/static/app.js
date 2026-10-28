/* Drama Studio 前端：原生 JS 单页应用 */
'use strict';

// ── 工具 ─────────────────────────────────────────────
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtTime = t => { const d = new Date(t * 1000); return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); };
const voiceLabel = id => {
  const v = state.voices.find(x => x.id === id);
  return v ? v.label : (id || '').replace(/^(ICL_)?zh_(fe)?male_?/, '').slice(0, 12);
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.status === 204 ? null : res.json();
}

// ── 全局状态 ─────────────────────────────────────────
const state = {
  project: null,
  stage: 'script',
  voices: [],
  jobs: new Map(),          // id -> job snapshot
  jobLogs: new Map(),       // id -> lines[]
  logTab: null,
  dirty: false,
  pendingSaveEl: null,
};

const STAGES = [
  { key: 'concept', label: '创意', icon: '💡' },
  { key: 'script', label: '剧本', icon: '📖' },
  { key: 'characters', label: '角色', icon: '🎭' },
  { key: 'shots', label: '分镜', icon: '🎬' },
  { key: 'voices', label: '配音', icon: '🎙️' },
  { key: 'segments', label: '片段', icon: '🎥' },
  { key: 'final', label: '成片', icon: '🏆' },
];

const projBusy = () =>
  state.project && [...state.jobs.values()].some(j => j.project_id === state.project.id && (j.status === 'running' || j.status === 'queued'));

// ── Toast / Confirm ──────────────────────────────────
function toast(msg, type = 'info', ms = 3200) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, ms);
}

function confirmBox(title, text) {
  return new Promise(resolve => {
    $('#confirmTitle').textContent = title;
    $('#confirmText').textContent = text;
    $('#confirmModal').hidden = false;
    const done = v => { $('#confirmModal').hidden = true; resolve(v); };
    $('#confirmOk').onclick = () => done(true);
    $('#confirmCancel').onclick = () => done(false);
  });
}

// ── 反馈弹窗：带用户反馈重新生成 ─────────────────────
function ensureFeedbackModal() {
  let m = $('#feedbackModal');
  if (m) return m;
  m = document.createElement('div');
  m.id = 'feedbackModal';
  m.className = 'modal-mask';
  m.hidden = true;
  m.innerHTML = `
    <div class="modal">
      <div class="modal-head">
        <h2 id="fbTitle">重新生成</h2>
        <button class="icon-btn" id="fbClose">✕</button>
      </div>
      <div class="modal-body">
        <p id="fbHint" class="muted" style="margin-bottom:14px"></p>
        <label class="field" id="fbVoiceWrap" style="margin:0 0 14px" hidden>
          <span>指定音色（可选，优先于文字反馈）</span>
          <select id="fbVoice"></select>
        </label>
        <label class="field" style="margin:0">
          <span>修改反馈（留空 = 按原样重新生成）</span>
          <textarea id="fbText" rows="3"></textarea>
        </label>
      </div>
      <div class="modal-foot">
        <button class="ghost-btn" id="fbCancel">取消</button>
        <button class="btn primary" id="fbSubmit">🚀 按反馈生成</button>
      </div>
    </div>`;
  document.body.appendChild(m);
  return m;
}

function askFeedback({ title, hint, placeholder, kind, options = {}, okMsg = '任务已提交', voicePicker = false }) {
  const m = ensureFeedbackModal();
  $('#fbTitle').textContent = title;
  $('#fbHint').textContent = hint || '';
  const vw = $('#fbVoiceWrap');
  const vs = $('#fbVoice');
  if (voicePicker) {
    vw.hidden = false;
    vs.innerHTML = `<option value="">不指定（按角色当前音色）</option>` +
      state.voices.map(v => `<option value="${v.id}">${esc(v.label)}</option>`).join('');
    vs.value = options.voice_type || '';
  } else {
    vw.hidden = true;
    vs.innerHTML = '';
  }
  const ta = $('#fbText');
  ta.value = '';
  ta.placeholder = placeholder || '描述你希望如何调整…';
  m.hidden = false;
  setTimeout(() => ta.focus(), 50);
  const close = () => { m.hidden = true; };
  $('#fbClose').onclick = close;
  $('#fbCancel').onclick = close;
  $('#fbSubmit').onclick = async () => {
    const feedback = ta.value.trim();
    const voice_type = voicePicker ? vs.value : '';
    close();
    await triggerJob(kind, { ...options, feedback, ...(voice_type ? { voice_type } : {}) }, okMsg);
  };
}

// ── SSE 事件流 ───────────────────────────────────────
function connectSSE() {
  const es = new EventSource('/api/events');
  es.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'hello') {
      ev.jobs.forEach(j => state.jobs.set(j.id, j));
      updateWorkerPill();
    } else if (ev.type === 'job') {
      state.jobs.set(ev.job.id, ev.job);
      if (ev.job.status === 'done') {
        toast(`✅ ${ev.job.title} 完成`, 'ok');
        if (!state.project && ev.job.kind === 'create_project') {
          renderHome();                    // 首页项目列表自动出现新项目
        } else {
          maybeRefreshProject(ev.job);
        }
        if (state.project && state.stage === 'characters') loadProject();
      } else if (ev.job.status === 'error') {
        toast(`❌ ${ev.job.title} 失败`, 'err', 6000);
        maybeRefreshProject(ev.job);
      } else if (state.project && state.stage === 'characters' && ev.job.kind === 'char_image') {
        loadProject();                    // 显示/取消"定妆照生成中"蒙层
      }
      updateWorkerPill();
      renderLogTabs();
    } else if (ev.type === 'log') {
      const arr = state.jobLogs.get(ev.job_id) || [];
      arr.push(ev.line);
      if (arr.length > 2000) arr.shift();
      state.jobLogs.set(ev.job_id, arr);
      if (state.logTab === ev.job_id) appendLogLine(ev.line);
      if ($('#logDrawer').classList.contains('open')) renderLogTabs();
    }
  };
  es.onerror = () => setTimeout(connectSSE, 3000);
}

let _refreshTimer = null;
function maybeRefreshProject(job) {
  if (!state.project || job.project_id !== state.project.id) return;
  clearTimeout(_refreshTimer);
  _refreshTimer = setTimeout(loadProject, 800);
}

function updateWorkerPill() {
  const busy = [...state.jobs.values()].some(j => j.status === 'running');
  $('#workerStatus').classList.toggle('busy', busy);
  $('#workerLabel').textContent = busy ? '任务执行中' : '引擎就绪';
}

// ── 路由 ─────────────────────────────────────────────
function hashRoute() {
  const h = location.hash.replace(/^#\/?/, '');
  if (h.startsWith('project/')) {
    const [, id, stage] = h.split('/');
    state.stage = STAGES.some(s => s.key === stage) ? stage : 'script';
    openWorkspace(id);
  } else {
    state.project = null;
    renderHome();
  }
}
window.addEventListener('hashchange', hashRoute);

// ── 未保存修改跟踪 ───────────────────────────────────
function findSaveEl(target) {
  const scope = target.closest('.shot-card, .char-card, .panel') || $('#stageBody');
  return scope.querySelector('[data-save], #saveScript, [data-savechar]');
}

function markDirty(target, saveEl) {
  state.dirty = true;
  state.pendingSaveEl = saveEl || findSaveEl(target);
  renderDirtyBar();
  if (state.pendingSaveEl) state.pendingSaveEl.classList.add('needs-save');
}

function clearDirty() {
  state.dirty = false;
  $$('.needs-save').forEach(el => el.classList.remove('needs-save'));
  state.pendingSaveEl = null;
  renderDirtyBar();
}

$('#view').addEventListener('input', e => {
  if (e.target.closest('input, textarea, select')) markDirty(e.target);
});
$('#view').addEventListener('change', e => {
  if (e.target.closest('input, textarea, select')) markDirty(e.target);
});
$('#view').addEventListener('click', e => {
  if (e.target.closest('.chip')) markDirty(e.target);
});

function renderDirtyBar() {
  let bar = $('#dirtyBar');
  if (!state.dirty) { bar?.remove(); return; }
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'dirtyBar';
    bar.className = 'dirty-bar';
    bar.innerHTML = `
      <span>⚠️ 有未保存的修改</span>
      <button class="btn primary sm" id="dirtySave">💾 保存</button>
      <button class="ghost-btn sm" id="dirtyDiscard">放弃</button>`;
    document.body.appendChild(bar);
    $('#dirtySave').onclick = () => {
      const btn = state.pendingSaveEl || $('#stageBody [data-save], #saveScript, [data-savechar]');
      btn?.click();
    };
    $('#dirtyDiscard').onclick = async () => {
      clearDirty();
      if (state.project) await loadProject();
    };
  }
}

// Cmd/Ctrl + S 保存
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
    e.preventDefault();
    const btn = state.pendingSaveEl ||
      $('#stageBody [data-save], #saveScript, [data-savechar]');
    btn?.click();
  }
});

// 切换_page前，如果有未保存修改先确认
document.addEventListener('click', e => {
  const nav = e.target.closest('.step, .ws-crumb a, .brand, .project-card');
  if (!nav || !state.dirty) return;
  e.preventDefault();
  e.stopPropagation();
  let desired = '';
  if (nav.tagName === 'A') desired = nav.getAttribute('href');
  else {
    const m = (nav.getAttribute('onclick') || '').match(/location\.hash='([^']+)'/);
    desired = m ? m[1] : '';
  }
  confirmBox('有未保存的修改', '先保存当前修改吗？取消则留在本页。').then(ok => {
    if (ok) {
      const btn = state.pendingSaveEl ||
        $('#stageBody [data-save], #saveScript, [data-savechar]');
      btn?.click();
      setTimeout(() => { if (desired) location.hash = desired; }, 1000);
    }
  });
}, true);

window.addEventListener('beforeunload', e => {
  if (state.dirty) { e.preventDefault(); e.returnValue = ''; }
});

async function renderHome() {
  const projects = await api('/api/projects');
  const cards = projects.map(p => {
    const done = (p.shots || []).filter(s => s.video_file).length;
    const total = (p.shots || []).length;
    const pct = total ? Math.round(done / total * 100) : 0;
    return `
      <div class="project-card" onclick="location.hash='#/project/${p.id}/script'">
        <div>
          <div class="pc-title">${esc(p.name || '未命名')}</div>
          <div class="pc-concept">${esc(p.concept)}</div>
        </div>
        <div class="pc-foot">
          <div class="progress-bar"><i style="width:${pct}%"></i></div>
          <span class="badge ${p.status}">${done}/${total} · ${statusLabel(p.status)}</span>
        </div>
      </div>`;
  }).join('');

  $('#view').innerHTML = `
    <section class="hero">
      <h1>用 AI 拍一部<span>会讲故事</span>的短剧</h1>
      <p>创意 → 剧本 → 角色 → 分镜 → 配音 → 视频片段 → 成片，每个环节都能人工干预、实时预览、逐条重做。</p>
      <button class="btn primary" id="newProjectBtn">✨ 新建短剧</button>
    </section>
    <div class="section-head">
      <h2>📂 我的项目</h2>
    </div>
    ${projects.length ? `<div class="project-grid">${cards}</div>` : `
      <div class="empty-state"><div class="big">🎞️</div>还没有项目，点击上方按钮开始第一部短剧</div>`}
  `;
  $('#newProjectBtn').onclick = openCreateModal;
}

function statusLabel(s) {
  return { created: '已创建', scripted: '剧本就绪', voiced: '配音完成', generating: '片段生成',
    assembled: '已成片', failed: '失败', done: '已完成', pending: '待生成', running: '生成中' }[s] || s;
}
function shotBadge(s) {
  const cls = { done: 'assembled', failed: 'failed', running: 'generating' }[s] || '';
  return `<span class="badge ${cls}">${statusLabel(s)}</span>`;
}

// ── 新建项目弹窗 ─────────────────────────────────────
function openCreateModal() {
  $('#createModal').hidden = false;
  $('#f_concept').focus();
}
$$('#createModal [data-close]').forEach(b => b.onclick = () => $('#createModal').hidden = true);
$('#f_shots').oninput = e => $('#f_shots_val').textContent = e.target.value;

$('#createSubmit').onclick = async () => {
  const concept = $('#f_concept').value.trim();
  if (concept.length < 2) return toast('请先填写一句话创意', 'err');
  const body = {
    concept,
    shots: +$('#f_shots').value,
    ratio: $('#f_ratio').value,
    resolution: $('#f_resolution').value,
    style: $('#f_style').value,
  };
  $('#createModal').hidden = true;
  try {
    const job = await api('/api/projects', { method: 'POST', body: JSON.stringify(body) });
    toast('🚀 已开始创作，可在右下角日志查看进度', 'info', 5000);
    openLogDrawer(job.id);
  } catch (e) { toast('创建失败：' + e.message, 'err'); }
};

// ── 工作区 ──────────────────────────────────────────
async function openWorkspace(id) {
  try {
    state.project = await api(`/api/projects/${id}`);
    if (!state.voices.length) state.voices = await api('/api/voices');
    renderWorkspace();
  } catch (e) {
    $('#view').innerHTML = `<div class="empty-state"><div class="big>⚠️</div>${esc(e.message)}</div>`;
  }
}

async function loadProject() {
  if (!state.project) return;
  try {
    state.project = await api(`/api/projects/${state.project.id}`);
    renderWorkspace();
  } catch {}
}

function stepState(p, key) {
  switch (key) {
    case 'concept': return true;
    case 'script': return !!p.script;
    case 'characters':
      return (p.script.characters || []).every(c => c.ref_image);
    case 'shots': return (p.shots || []).length > 0;
    case 'voices':
      return (p.shots || []).every(s => (s.voices || []).length === (s.dialogues || []).filter(d => d.text).length);
    case 'segments': return (p.shots || []).every(s => s.video_file);
    case 'final': return !!p.final_video;
  }
  return false;
}

function renderWorkspace() {
  const p = state.project;
  const busy = projBusy();

  const stepsHtml = STAGES.map((s, i) => {
    const done = stepState(p, s.key);
    const active = s.key === state.stage;
    return `
      ${i ? `<div class="step-line ${stepState(p, STAGES[i - 1].key) ? 'done' : ''}"></div>` : ''}
      <div class="step ${active ? 'active' : ''} ${done ? 'done' : ''}"
           onclick="location.hash='#/project/${p.id}/${s.key}'">
        <span class="s-icon">${done ? '✓' : s.icon}</span>
        <span class="s-label">${s.label}</span>
      </div>`;
  }).join('');

  $('#view').innerHTML = `
    <div class="ws-head">
      <div class="ws-crumb"><a href="#/home">📂 项目</a> / ${esc(p.name)}</div>
      <div class="ws-title-row">
        <div>
          <h1>${esc(p.name)}</h1>
          <div class="ws-meta">
            <span class="badge ${p.status}">${statusLabel(p.status)}</span>
            <span class="badge">${p.ratio}</span>
            <span class="badge">${p.resolution}</span>
            <span class="badge">${(p.shots || []).length} 镜</span>
          </div>
        </div>
        <div class="ws-actions">
          <button class="btn violet" id="btnRunAll" ${busy ? 'disabled' : ''}>⚡ 一键补齐并合成</button>
        </div>
      </div>
    </div>
    <div class="stepper">${stepsHtml}</div>
    <div class="stage" id="stageBody"></div>
  `;

  $('#btnRunAll').onclick = async () => {
    if (!await confirmBox('一键补齐并合成？', '将自动生成缺失的配音、视频片段并合成成片，耗时较长。')) return;
    await triggerJob('run_remaining', {}, '已开始自动流程');
  };

  renderStage();
}

async function triggerJob(kind, options = {}, okMsg = '任务已提交') {
  const p = state.project;
  try {
    const job = await api(`/api/projects/${p.id}/jobs`, {
      method: 'POST', body: JSON.stringify({ kind, options }),
    });
    toast(okMsg, 'ok');
    openLogDrawer(job.id);
    return job;
  } catch (e) { toast('提交失败：' + e.message, 'err'); }
}

// ── 各环节渲染 ───────────────────────────────────────
function renderStage() {
  const p = state.project;
  const el = $('#stageBody');
  switch (state.stage) {
    case 'concept': el.innerHTML = viewConcept(p); bindScript(); break;
    case 'script': el.innerHTML = viewScript(p); bindScript(p); break;
    case 'characters': el.innerHTML = viewCharacters(p); bindCharacters(p); break;
    case 'shots': el.innerHTML = viewShots(p); bindShots(p); break;
    case 'voices': el.innerHTML = viewVoices(p); break;
    case 'segments': el.innerHTML = viewSegments(p); break;
    case 'final': el.innerHTML = viewFinal(p); break;
  }
}

// 创意
function viewConcept(p) {
  return `
    <div class="panel">
      <div class="panel-title"><h3>💡 核心创意</h3></div>
      <p style="font-size:18px;line-height:1.9">${esc(p.concept)}</p>
      <div class="grid-2" style="margin-top:22px">
        <div class="field"><span>风格倾向</span><input value="${esc(p.style)}" disabled /></div>
        <div class="field"><span>分镜数量</span><input value="${p.num_shots}" disabled /></div>
        <div class="field"><span>画面比例</span><input value="${p.ratio}" disabled /></div>
        <div class="field"><span>分辨率</span><input value="${p.resolution}" disabled /></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title"><h3>♻️ 重新开始</h3></div>
      <p class="muted">对当前剧本不满意？可让 AI 依据同一创意重新生成剧本、分镜与角色定妆照。</p>
      <div style="margin-top:14px">
        <button class="btn danger" id="btnReScript">🗯 AI 重新生成剧本</button>
      </div>
    </div>`;
}

// 剧本
function viewScript(p) {
  const s = p.script || {};
  return `
    <div class="panel">
      <div class="panel-title">
        <h3>📖 剧本设定</h3>
        <button class="btn primary sm" id="saveScript">💾 保存修改</button>
      </div>
      <div class="grid-2">
        <label class="field"><span>片名</span><input id="s_title" value="${esc(s.title)}" /></label>
        <label class="field"><span>题材</span><input id="s_genre" value="${esc(s.genre)}" /></label>
      </div>
      <label class="field"><span>一句话梗概</span><input id="s_logline" value="${esc(s.logline)}" /></label>
      <label class="field"><span>核心主题</span><input id="s_theme" value="${esc(s.theme)}" /></label>
      <label class="field"><span>风格锚点（全片视觉基调，会前置到每个镜头 prompt）</span>
        <textarea id="s_style_anchor" rows="3">${esc(s.style_anchor)}</textarea></label>
      <label class="field" style="max-width:260px"><span>BGM 风格</span>
        <select id="s_bgm">
          ${['gufeng', 'epic', 'business', 'bright', 'suspense'].map(v =>
            `<option ${s.bgm_style === v ? 'selected' : ''}>${v}</option>`).join('')}
        </select></label>
    </div>`;
}

function bindScript() {
  const saveBtn = $('#saveScript');
  if (saveBtn) saveBtn.onclick = async () => {
      const body = {
        title: $('#s_title').value,
        genre: $('#s_genre').value,
        logline: $('#s_logline').value,
        theme: $('#s_theme').value,
        style_anchor: $('#s_style_anchor').value,
        bgm_style: $('#s_bgm').value,
      };
      try {
        state.project = await api(`/api/projects/${state.project.id}/script`, {
          method: 'PUT', body: JSON.stringify(body),
        });
        toast('剧本已保存', 'ok');
        clearDirty();
        renderWorkspace();
      } catch (e) { toast(e.message, 'err'); }
    };
  const btn = $('#btnReScript');
  if (btn) btn.onclick = () => askFeedback({
    title: '🗯 AI 重新生成剧本',
    hint: '按你的反馈调整剧本与分镜，并重新生成角色定妆照；已生成的配音/片段不受影响但可能不再匹配。',
    placeholder: '例如：结局改成大团圆；女主性格再强势一些；中段加一个反转；分镜减到5个…',
    kind: 'regenerate_script',
    okMsg: '剧本调整中',
  });
}

// 角色
function viewCharacters(p) {
  const chars = (p.script.characters || []);
  const busyNames = new Set(
    [...state.jobs.values()]
      .filter(j => (j.status === 'running' || j.status === 'queued') && j.kind === 'char_image')
      .map(j => j.title.replace(/^定妆照：/, ''))
  );
  return `
    <div class="panel-title" style="padding:0 2px">
      <h3>🎭 角色设定（外观描述用于锁定每个镜头的人物一致性）</h3>
    </div>
    <datalist id="voiceList">
      ${state.voices.map(v => `<option value="${v.id}">${v.label}</option>`).join('')}
    </datalist>
    <div class="char-grid">
      ${chars.map((c, i) => `
        <div class="char-card">
          <div class="char-img-wrap">
            ${c.ref_image
              ? `<img class="char-img" src="${c.ref_image}" alt="${esc(c.name)}"
                   data-preview="${c.ref_image}" data-name="${esc(c.name)}" title="点击放大预览" />`
              : `<div class="char-img-placeholder">👤</div>`}
            ${busyNames.has(c.name) ? `
              <div class="img-loading">
                <span class="spinner"></span>
                <span>定妆照生成中…</span>
              </div>` : ''}
            ${c.ref_image && !busyNames.has(c.name) ? `<div class="img-zoom-hint">🔍 点击放大</div>` : ''}
          </div>
          <div class="char-body">
            <h4>${esc(c.name)}</h4>
            <div class="role">${esc(c.role || '')} · ${esc(c.tag || '')}</div>
            <label class="field"><span>记忆点标签</span><input data-cf="tag" data-i="${i}" value="${esc(c.tag)}" /></label>
            <label class="field"><span>外观锁定描述</span>
              <textarea data-cf="appearance" data-i="${i}" rows="4">${esc(c.appearance)}</textarea></label>
            <label class="field"><span>音色 ID</span>
              <input data-cf="voice_type" data-i="${i}" value="${esc(c.voice_type)}"
                list="voiceList" /></label>
            <div class="char-actions">
              <button class="btn primary sm" data-savechar="${i}">💾 保存</button>
              <button class="ghost-btn sm" data-reimg="${i}">🖼 重生成定妆照</button>
            </div>
          </div>
        </div>`).join('')}
    </div>`;
}

function bindCharacters() {
  const p = state.project;
  const busyNames = new Set(
    [...state.jobs.values()]
      .filter(j => (j.status === 'running' || j.status === 'queued') && j.kind === 'char_image')
      .map(j => j.title.replace(/^定妆照：/, ''))
  );
  $$('[data-savechar]').forEach(btn => {
    btn.onclick = async () => {
      const i = +btn.dataset.savechar;
      const name = p.script.characters[i].name;
      const body = {};
      $$(`[data-cf][data-i="${i}"]`).forEach(inp => body[inp.dataset.cf] = inp.value);
      try {
        state.project = await api(`/api/projects/${p.id}/characters/${encodeURIComponent(name)}`, {
          method: 'PUT', body: JSON.stringify(body),
        });
        toast('角色已保存，镜头 prompt 已同步更新', 'ok');
        clearDirty();
        renderWorkspace();
      } catch (e) { toast(e.message, 'err'); }
    };
  });
  $$('[data-reimg]').forEach(btn => {
    btn.onclick = () => {
      const i = +btn.dataset.reimg;
      const name = p.script.characters[i].name;
      if (busyNames.has(name)) return toast('该角色定妆照正在生成中', 'err');
      if (projBusy()) return toast('请等待当前任务完成', 'err');
      askFeedback({
        title: `🖼 重生成「${name}」定妆照`,
        hint: '按你的反馈重新出图，仍保持单人胸像构图。',
        placeholder: '例如：更年轻一些；换成白色衣服；笑容再明显一点；背景换成室外…',
        kind: 'char_image',
        options: { name },
        okMsg: '定妆照生成中',
      });
    };
  });
}

// ── 图片灯箱预览（点击定妆照放大） ───────────────────
document.addEventListener('click', e => {
  const img = e.target.closest('[data-preview]');
  if (img) openLightbox(img.dataset.preview, img.dataset.name);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeLightbox();
});

function openLightbox(src, name) {
  let box = $('#lightbox');
  if (!box) {
    box = document.createElement('div');
    box.id = 'lightbox';
    box.className = 'lightbox';
    box.innerHTML = `
      <div class="lightbox-bar">
        <span id="lightboxName"></span>
        <button class="icon-btn" id="lightboxClose" title="关闭 (Esc)">✕</button>
      </div>
      <img id="lightboxImg" alt="preview" />`;
    document.body.appendChild(box);
    box.onclick = ev => { if (ev.target === box || ev.target.id === 'lightboxClose') closeLightbox(); };
  }
  $('#lightboxName').textContent = name || '';
  $('#lightboxImg').src = src;
  box.classList.add('open');
}

function closeLightbox() {
  $('#lightbox')?.classList.remove('open');
}

// 分镜
function viewShots(p) {
  const chars = p.script.characters || [];
  return `
    <div class="panel-title" style="padding:0 2px">
      <h3>🎬 分镜脚本（可编辑场景/动作/对白，并单独生成配音与视频）</h3>
      <button class="btn violet sm" id="addShotBtn">➕ 添加镜头</button>
    </div>
    ${p.shots.map((s, i) => {
      const idx = i + 1;
      return `
      <div class="shot-card" data-shot="${i}">
        <div class="shot-head">
          <h4><span class="shot-idx">${idx}</span>
            <button type="button" class="drag-handle" data-drag title="按住拖动排序">⠿</button>
            <input data-f="title" value="${esc(s.title)}"
              style="background:transparent;border:none;color:inherit;font:inherit;font-weight:700;width:220px;outline:none" />
          </h4>
          ${shotBadge(s.video_file && s.status === 'pending' ? 'done' : s.status)}
        </div>
        <div class="grid-2">
          <label class="field"><span>场景</span><textarea data-f="scene" rows="2">${esc(s.scene)}</textarea></label>
          <label class="field"><span>动作 / 镜头运动</span><textarea data-f="action" rows="2">${esc(s.action)}</textarea></label>
          <label class="field"><span>情绪</span><input data-f="emotion" value="${esc(s.emotion)}" /></label>
          <label class="field"><span>时长(秒)</span><input data-f="duration" type="number" min="4" max="10" value="${s.duration || 10}" /></label>
        </div>
        <div class="field">
          <span>出场角色</span>
          <div class="char-chips">
            ${chars.map(c => `
              <button type="button" class="chip ${(s.characters || []).includes(c.name) ? 'on' : ''}"
                data-char="${esc(c.name)}">${esc(c.name)}</button>`).join('')}
          </div>
        </div>
        <div class="field">
          <span>对白</span>
          <div class="dialogues">
            ${(s.dialogues || []).map(d => dialogueRow(d, chars)).join('')}
          </div>
          <button type="button" class="ghost-btn sm" data-add-dialogue style="margin-top:6px;align-self:flex-start">➕ 添加对白</button>
        </div>
        <div class="prompt-box">
          <b>视频 Prompt：</b>${esc(s.prompt || '保存后自动生成')}
        </div>
        <div class="shot-tools" style="margin-top:16px">
          <button class="btn primary sm" data-save>💾 保存镜头</button>
          <button class="ghost-btn sm" data-voice>🎙 生成配音</button>
          <button class="ghost-btn sm" data-video>🎥 ${s.video_file ? '重新生成视频' : '生成视频'}</button>
          <button class="ghost-btn sm danger-text" data-del>🗑 删除镜头</button>
        </div>
      </div>`;
    }).join('')}`;
}

function dialogueRow(d, chars) {
  return `
    <div class="dialogue-row">
      <select data-d="character">
        ${chars.map(c => `<option ${d.character === c.name ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}
      </select>
      <input data-d="text" value="${esc(d.text)}" placeholder="对白内容" />
      <input data-d="start_offset" type="number" step="0.5" min="0" max="9" value="${d.start_offset ?? 2.5}" title="镜头开始后几秒" />
      <button type="button" class="icon-btn" data-del-dialogue title="删除">✕</button>
    </div>`;
}

// 添加镜头：先描述需求 → AI 自动生成场景 → 可编辑确认后追加
function openAddShotModal() {
  const p = state.project;
  const chars = p.script.characters || [];
  let draft = null;

  const mask = document.createElement('div');
  mask.className = 'modal-mask';
  document.body.appendChild(mask);
  const close = () => mask.remove();

  // 删除对白的事件委托：mask 只创建一次，避免 innerHTML 重渲染后重复绑定
  mask.addEventListener('click', e => {
    if (e.target.matches('[data-del-dialogue]')) e.target.closest('.dialogue-row').remove();
  });

  function viewInput() {
    return `
      <div class="modal">
        <div class="modal-head">
          <h2>➕ 添加镜头</h2>
          <button class="icon-btn" id="asClose">✕</button>
        </div>
        <div class="modal-body">
          <label class="field" style="margin:0">
            <span>描述你想要的镜头，AI 会结合本片风格与角色自动生成场景/动作/对白</span>
            <textarea id="asPrompt" rows="4"
              placeholder="例如：雨夜，两人在天台对峙，气氛紧张但不动手；男主转头望向城市灯火，平静地说出心里话…"></textarea>
          </label>
          <p class="muted as-tip">💡 描述越具体（时间/地点/人物/情绪/动作），生成效果越好；不需要对白可注明「无对白」。</p>
        </div>
        <div class="modal-foot">
          <button class="ghost-btn" id="asBlank">空白镜头</button>
          <button class="btn primary" id="asGenerate">✨ AI 自动生成场景</button>
        </div>
      </div>`;
  }

  function viewEdit(shot) {
    return `
      <div class="modal">
        <div class="modal-head">
          <h2>➕ 添加镜头 · 确认内容</h2>
          <button class="icon-btn" id="asClose">✕</button>
        </div>
        <div class="modal-body">
          <label class="field"><span>标题</span>
            <input data-asf="title" value="${esc(shot.title)}" /></label>
          <div class="grid-2">
            <label class="field"><span>场景</span><textarea data-asf="scene" rows="2">${esc(shot.scene)}</textarea></label>
            <label class="field"><span>动作 / 镜头运动</span><textarea data-asf="action" rows="2">${esc(shot.action)}</textarea></label>
            <label class="field"><span>情绪</span><input data-asf="emotion" value="${esc(shot.emotion)}" /></label>
            <label class="field"><span>时长(秒)</span><input data-asf="duration" type="number" min="4" max="10" value="${shot.duration || 10}" /></label>
          </div>
          <div class="field">
            <span>出场角色</span>
            <div class="char-chips">
              ${chars.map(c => `
                <button type="button" class="chip ${(shot.characters || []).includes(c.name) ? 'on' : ''}"
                  data-char="${esc(c.name)}">${esc(c.name)}</button>`).join('')}
            </div>
          </div>
          <div class="field">
            <span>对白</span>
            <div class="dialogues" id="asDialogues">
              ${(shot.dialogues || []).map(d => dialogueRow(d, chars)).join('')}
            </div>
            <button type="button" class="ghost-btn sm" id="asAddDialogue" style="margin-top:6px;align-self:flex-start">➕ 添加对白</button>
          </div>
        </div>
        <div class="modal-foot">
          <button class="ghost-btn" id="asBack">↩ 重新描述</button>
          <button class="btn primary" id="asConfirm">➕ 确认添加</button>
        </div>
      </div>`;
  }

  function bindEdit() {
    $('#asClose').onclick = close;
    $('#asBack').onclick = () => { draft = null; render(); };

    $$('.chip', mask).forEach(chip => chip.onclick = () => chip.classList.toggle('on'));
    $('#asAddDialogue').onclick = () => {
      const d = { character: (chars[0] || {}).name || '', text: '', start_offset: 2.5 };
      $('#asDialogues').insertAdjacentHTML('beforeend', dialogueRow(d, chars));
    };

    $('#asConfirm').onclick = async () => {
      const body = {
        title: $('[data-asf="title"]', mask).value,
        scene: $('[data-asf="scene"]', mask).value,
        action: $('[data-asf="action"]', mask).value,
        emotion: $('[data-asf="emotion"]', mask).value,
        duration: +$('[data-asf="duration"]', mask).value || 10,
        characters: $$('.chip.on', mask).map(c => c.dataset.char),
        dialogues: $$('.dialogue-row', mask).map(row => ({
          character: $('[data-d="character"]', row).value,
          text: $('[data-d="text"]', row).value,
          start_offset: +$('[data-d="start_offset"]', row).value,
        })).filter(d => d.text.trim()),
      };
      const btn = $('#asConfirm');
      btn.disabled = true;
      try {
        state.project = await api(`/api/projects/${p.id}/shots`, {
          method: 'POST', body: JSON.stringify(body),
        });
        close();
        renderWorkspace();
        toast('镜头已添加，prompt 已生成', 'ok');
      } catch (e) {
        btn.disabled = false;
        toast(e.message, 'err');
      }
    };
  }

  function render() {
    mask.innerHTML = draft === null ? viewInput() : viewEdit(draft);
    if (draft === null) {
      $('#asClose').onclick = close;
      $('#asBlank').onclick = () => {
        draft = { title: '新增镜头', scene: '', action: '', emotion: '自然',
                  duration: 10, characters: [], dialogues: [] };
        render();
      };
      $('#asGenerate').onclick = async () => {
        const prompt = $('#asPrompt').value.trim();
        if (prompt.length < 2) { toast('请先描述想要的镜头', 'err'); return; }
        const btn = $('#asGenerate');
        btn.disabled = true;
        btn.textContent = '⏳ AI 生成中…';
        try {
          draft = await api(`/api/projects/${p.id}/shots/generate`, {
            method: 'POST', body: JSON.stringify({ prompt }),
          });
          render();
        } catch (e) {
          btn.disabled = false;
          btn.textContent = '✨ AI 自动生成场景';
          toast(e.message, 'err');
        }
      };
      $('#asPrompt').focus();
    } else {
      bindEdit();
    }
  }

  render();
}

function bindShots() {
  const p = state.project;

  $('#addShotBtn')?.addEventListener('click', () => openAddShotModal());

  $$('.shot-card').forEach(card => {
    const i = +card.dataset.shot;

    $$('.chip', card).forEach(chip => chip.onclick = () => chip.classList.toggle('on'));

    // 拖拽排序：仅从手柄起拖；有未保存修改时阻止
    const dragHandle = $('[data-drag]', card);
    dragHandle?.addEventListener('mousedown', () => { card.draggable = true; });
    card.addEventListener('dragstart', e => {
      if (state.dirty) {
        e.preventDefault();
        card.draggable = false;
        toast('请先保存当前修改，再拖动排序', 'err');
        return;
      }
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      try { e.dataTransfer.setData('text/plain', String(i)); } catch { /* Firefox */ }
    });
    card.addEventListener('dragover', e => {
      if (!$$('.shot-card').some(c => c.classList.contains('dragging'))) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const rect = card.getBoundingClientRect();
      const before = e.clientY < rect.top + rect.height / 2;
      card.classList.toggle('drop-before', before);
      card.classList.toggle('drop-after', !before);
    });
    card.addEventListener('dragleave', () => {
      card.classList.remove('drop-before', 'drop-after');
    });
    card.addEventListener('drop', e => {
      const draggingCard = $$('.shot-card').find(c => c.classList.contains('dragging'));
      if (!draggingCard) return;
      e.preventDefault();
      if (draggingCard === card) {
        $$('.shot-card').forEach(c => c.classList.remove('drop-before', 'drop-after', 'dragging'));
        card.draggable = false;
        return;
      }
      const from = +draggingCard.dataset.shot;
      const n = p.shots.length;
      const rect = card.getBoundingClientRect();
      const before = e.clientY < rect.top + rect.height / 2;

      const order = [...Array(n).keys()];
      order.splice(from, 1);
      let to = from < i ? i - 1 : i;
      if (!before) to += 1;
      to = Math.max(0, Math.min(n - 1, to));
      order.splice(to, 0, from);

      $$('.shot-card').forEach(c => c.classList.remove('drop-before', 'drop-after', 'dragging'));
      card.draggable = false;

      (async () => {
        try {
          state.project = await api(`/api/projects/${p.id}/shots/reorder`, {
            method: 'POST', body: JSON.stringify({ order: order.map(x => x + 1) }),
          });
          renderWorkspace();
          toast('镜头顺序已更新', 'ok');
        } catch (err) {
          toast(err.message, 'err');
          await loadProject();
        }
      })();
    });
    card.addEventListener('dragend', () => {
      card.draggable = false;
      card.classList.remove('dragging', 'drop-before', 'drop-after');
    });

    $('[data-add-dialogue]', card).onclick = () => {
      const d = { character: (p.script.characters[0] || {}).name || '', text: '', start_offset: 2.5 };
      $('.dialogues', card).insertAdjacentHTML('beforeend', dialogueRow(d, p.script.characters));
    };

    card.addEventListener('click', e => {
      if (e.target.matches('[data-del-dialogue]')) e.target.closest('.dialogue-row').remove();
    });

    $('[data-save]', card).onclick = async () => {
      const body = {
        title: $('[data-f="title"]', card).value,
        scene: $('[data-f="scene"]', card).value,
        action: $('[data-f="action"]', card).value,
        emotion: $('[data-f="emotion"]', card).value,
        duration: +$('[data-f="duration"]', card).value,
        characters: $$('.chip.on', card).map(c => c.dataset.char),
        dialogues: $$('.dialogue-row', card).map(row => ({
          character: $('[data-d="character"]', row).value,
          text: $('[data-d="text"]', row).value,
          start_offset: +$('[data-d="start_offset"]', row).value,
        })).filter(d => d.text.trim()),
      };
      try {
        state.project = await api(`/api/projects/${p.id}/shots/${i + 1}`, {
          method: 'PUT', body: JSON.stringify(body),
        });
        toast('镜头已保存，prompt 已重建', 'ok');
        clearDirty();
        renderWorkspace();
      } catch (e) { toast(e.message, 'err'); }
    };

    $('[data-voice]', card).onclick = () => askFeedback({
      title: `🎙 重新生成镜头 ${i + 1} 配音`,
      hint: '可直接在下方下拉选择正确音色；也可在反馈里写"换成温柔女声/御姐/少女音"等，还支持语速、音调、音量调整。',
      placeholder: '例如：换成温柔女声；语速慢一点；声音更低沉；音量再大一点…',
      kind: 'voices',
      options: { scope: 'shot', shot: i + 1 },
      okMsg: '配音生成中',
      voicePicker: true,
    });

    $('[data-video]', card).onclick = () => askFeedback({
      title: `🎥 重新生成镜头 ${i + 1} 视频`,
      hint: '反馈会追加到该镜头的视频生成 prompt；角色外观保持一致。',
      placeholder: '例如：镜头再拉近一些；改成夜晚；雨下大一点；人物表情再激动…',
      kind: 'video',
      options: { scope: 'shot', shot: i + 1, force: !!p.shots[i].video_file },
      okMsg: '视频生成中',
    });

    $('[data-del]', card).onclick = async () => {
      if (!await confirmBox('删除该镜头？', '删除后后续镜头序号将前移，对应素材文件会保留在磁盘上。')) return;
      try {
        state.project = await api(`/api/projects/${p.id}/shots/${i + 1}`, { method: 'DELETE' });
        renderWorkspace();
      } catch (e) { toast(e.message, 'err'); }
    };
  });
}

// 配音
function viewVoices(p) {
  return `
    <div class="panel-title" style="padding:0 2px">
      <h3>🎙️ 对白配音（先生成配音确定时长，视频才能精确对齐）</h3>
      <button class="btn primary sm" id="genAllVoices">🎙 全部生成配音</button>
    </div>
    ${p.shots.map((s, i) => `
      <div class="panel voice-group">
        <div class="panel-title">
          <h3>镜头 ${i + 1} · ${esc(s.title)}</h3>
          <button class="ghost-btn sm" data-shot-voice="${i}">生成该镜头配音</button>
        </div>
        ${(s.voices || []).length
          ? s.voices.map(v => `
            <div class="voice-line">
              <span class="vchar">${esc(v.character)}</span>
              <audio controls preload="none" src="${v.voice_file}"></audio>
              <span class="muted">${v.voice_type ? `<span class="voice-tag" title="${esc(v.voice_type)}">🔊${esc(voiceLabel(v.voice_type))}</span> · ` : ''}${v.duration}s · @${v.start_offset}s｜${esc(v.text)}</span>
            </div>`).join('')
          : `<p class="muted">暂无配音${s.dialogues && s.dialogues.length ? '，点击右上角生成' : '（该镜头无对白）'}</p>`}
      </div>`).join('')}`;
}

document.addEventListener('click', e => {
  const b = e.target.closest('[data-shot-voice]');
  if (!b || !state.project) return;
  askFeedback({
    title: `🎙 镜头 ${+b.dataset.shotVoice + 1} 配音`,
    hint: '可直接选择正确音色，或在反馈里写"换成女声/男声、御姐、少女音"等。',
    placeholder: '例如：换成温柔女声；语速慢一点；声音更低沉…',
    kind: 'voices',
    options: { scope: 'shot', shot: +b.dataset.shotVoice + 1 },
    okMsg: '配音任务已提交',
    voicePicker: true,
  });
});
$('#view').addEventListener('click', e => {
  if (e.target.id === 'genAllVoices') askFeedback({
    title: '🎙 全部配音',
    hint: '指定音色会覆盖所有角色（通常只用于单角色项目）；建议单条重生成。反馈会应用到每一条对白并重新合成。',
    placeholder: '例如：整体语速慢一点；都换成温柔女声（留空则只补齐缺失配音）',
    kind: 'voices',
    okMsg: '全部配音任务已提交',
    voicePicker: true,
  });
});

// 视频片段
function viewSegments(p) {
  return `
    <div class="panel-title" style="padding:0 2px">
      <h3>🎥 视频片段</h3>
      <button class="btn primary sm" id="genAllSeg">🎥 全部生成片段</button>
    </div>
    <div class="seg-grid">
      ${p.shots.map((s, i) => `
        <div class="seg-card">
          ${s.video_file
            ? `<video controls preload="none" src="${s.video_file}#t=0.1"></video>`
            : `<div class="seg-empty"><span style="font-size:34px">🎞</span><span>镜头 ${i + 1} 尚未生成</span></div>`}
          <div class="seg-meta">
            <h5><span>镜头 ${i + 1} · ${esc(s.title)}</span>${shotBadge(s.status)}</h5>
            <div class="seg-actions">
              <button class="ghost-btn sm" data-seg-gen="${i}" data-force="${s.video_file ? 1 : 0}">
                ${s.video_file ? '🔄 重新生成' : '🎬 生成'}</button>
            </div>
          </div>
        </div>`).join('')}
    </div>`;
}

$('#view').addEventListener('click', e => {
  if (!state.project) return;
  if (e.target.id === 'genAllSeg') askFeedback({
    title: '🎥 全部视频片段',
    hint: '反馈会追加到每一个镜头的生成 prompt；已存在的片段也会按反馈重生成。',
    placeholder: '例如：整体色调再暖一点；镜头都放慢一些（留空则只补齐缺失片段）',
    kind: 'video',
    okMsg: '全部片段任务已提交',
  });
  const b = e.target.closest('[data-seg-gen]');
  if (b) askFeedback({
    title: `🎥 镜头 ${+b.dataset.segGen + 1} 视频`,
    hint: '反馈会追加到该镜头的视频生成 prompt。',
    placeholder: '例如：镜头再拉近；改成雨夜；动作再激烈一点…',
    kind: 'video',
    options: { scope: 'shot', shot: +b.dataset.segGen + 1, force: b.dataset.force === '1' },
    okMsg: '片段任务已提交',
  });
});

// 成片
function viewFinal(p) {
  return `
    <div class="panel-title" style="padding:0 2px"><h3>🏆 最终成片</h3></div>
    ${p.final_video
      ? `<video class="final-video" controls src="${p.final_video}#t=0.1"></video>
         <p class="muted" style="margin-top:14px">📁 ${esc(p.final_video)}</p>`
      : `<div class="final-empty">
           <div class="big">🎬</div>
           <p class="muted" style="margin-bottom:20px">还没有成片。所有片段就绪后即可合成（片头片尾 + 转场 + 对白对齐 + BGM）。</p>
           <button class="btn primary" id="btnCompose" style="margin-right:10px">🎞 合成成片</button>
           <button class="btn violet" id="btnComposeAll">⚡ 补齐缺失并合成</button>
         </div>`}`;
}

$('#view').addEventListener('click', e => {
  if (!state.project) return;
  if (e.target.id === 'btnCompose') triggerJob('compose', {}, '合成任务已提交');
  if (e.target.id === 'btnComposeAll') triggerJob('run_remaining', {}, '自动流程已启动');
});

// ── 日志抽屉 ─────────────────────────────────────────
$('#logToggle').onclick = () => openLogDrawer();
$('#logClose').onclick = () => $('#logDrawer').classList.remove('open');

function openLogDrawer(jobId) {
  $('#logDrawer').classList.add('open');
  if (jobId) state.logTab = jobId;
  renderLogTabs();
}

function renderLogTabs() {
  const recent = [...state.jobs.values()].reverse().slice(0, 12);
  if (!state.logTab && recent[0]) state.logTab = recent[0].id;
  $('#logTabs').innerHTML = recent.map(j => `
    <button class="log-tab ${j.id === state.logTab ? 'active' : ''}" data-job="${j.id}">
      ${j.status === 'running' ? '🟡' : j.status === 'done' ? '🟢' : j.status === 'error' ? '🔴' : '⚪'}
      ${esc(j.title.slice(0, 12))}</button>`).join('');
  $$('#logTabs .log-tab').forEach(t => t.onclick = () => selectLogTab(t.dataset.job));
  selectLogTab(state.logTab, true);
}

async function selectLogTab(jobId, keepScroll) {
  if (!jobId) return;
  state.logTab = jobId;
  $$('#logTabs .log-tab').forEach(t => t.classList.toggle('active', t.dataset.job === jobId));
  let lines = state.jobLogs.get(jobId);
  if (!lines || lines.length < 50) {
    try {
      const full = await api(`/api/jobs/${jobId}`);
      lines = full.logs;
      state.jobLogs.set(jobId, lines);
    } catch { lines = lines || []; }
  }
  const body = $('#logBody');
  const stick = body.scrollHeight - body.scrollTop - body.clientHeight < 80;
  body.innerHTML = lines.map(l =>
    `<div class="log-line"><span class="t">${new Date(l.t * 1000).toLocaleTimeString('zh-CN')}</span>${esc(l.msg)}</div>`
  ).join('');
  if (stick || !keepScroll) body.scrollTop = body.scrollHeight;
}

function appendLogLine(line) {
  const body = $('#logBody');
  const stick = body.scrollHeight - body.scrollTop - body.clientHeight < 80;
  body.insertAdjacentHTML('beforeend',
    `<div class="log-line"><span class="t">${new Date(line.t * 1000).toLocaleTimeString('zh-CN')}</span>${esc(line.msg)}</div>`);
  if (stick) body.scrollTop = body.scrollHeight;
}

// ── 启动 ─────────────────────────────────────────────
api('/api/jobs').then(js => js.forEach(j => state.jobs.set(j.id, j)));
connectSSE();
hashRoute();
