/* Podcast Studio 前端：原生 JS 单页应用 */
'use strict';
const BUILD = '20261113a';
try {
  if (localStorage.getItem('pstudio_build') !== BUILD) {
    localStorage.setItem('pstudio_build', BUILD);
    location.replace(location.pathname + '?b=' + BUILD);
  }
} catch {}

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.status === 204 ? null : res.json();
}
function toast(msg, type = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  $('#toastBox').appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 3800);
}
const fmtDur = s => {
  s = Number(s) || 0;
  const m = Math.floor(s / 60), ss = Math.round(s % 60);
  return `${m}:${String(ss).padStart(2, '0')}`;
};
const fmtSize = b => b < 1024 * 1024
  ? (b / 1024).toFixed(0) + ' KB' : (b / 1024 / 1024).toFixed(1) + ' MB';
const fmtDate = t => {
  const d = new Date(t * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
};

const HOST_A = 'zh_male_shenyeboke_moon_bigtts';      // 深夜播客
const HOST_B = 'zh_female_zhixingnvsheng_mars_bigtts'; // 知性女声
const SAMPLE_SAY = '你好，欢迎收听本期节目，我是你的专属主播。';

const state = {
  view: 'create',
  voices: [], vmap: new Map(),
  voiceOpts: '',
  title: '我的第一期播客',
  hosts: [HOST_A, HOST_B],
  segments: [{ text: '', voice: HOST_A }],
  params: { speed: 1, volume: 1, pitch: 1 },
  jobs: new Map(),
  pending: new Map(),   // jobId → {type, idx?, voice?}
  logJobId: '',
  lastEpisode: null,
  library: { clips: [], episodes: [] },
  vq: '', vlang: '全部', vscene: '全部', sampleText: SAMPLE_SAY,
  libTab: 'episodes',
  ai: { mode: 'dialogue', style: 'chat', turns: 12,
        styles: [], loaded: false, busy: false },
};

// ── SSE ──────────────────────────────────────────────
function connectSSE() {
  const es = new EventSource('/api/events');
  es.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'hello') {
      ev.jobs.forEach(j => state.jobs.set(j.id, j));
      // 刷新页面后重建对「进行中任务」的追踪（仅可无上下文恢复的类型）
      ev.jobs.forEach(j => {
        if (j.status === 'queued' || j.status === 'running') {
          if (j.kind === 'aiscript') state.pending.set(j.id, { type: 'aiscript' });
          else if (j.kind === 'episode') state.pending.set(j.id, { type: 'ep' });
        }
      });
      updatePill();
    } else if (ev.type === 'job') {
      state.jobs.set(ev.job.id, ev.job);
      updatePill();
      if (state.pending.get(ev.job.id)?.type === 'aiscript' &&
          state.view === 'create') renderEpisodeStage();
      if (ev.job.status === 'done') onJobDone(ev.job.id);
      if (ev.job.status === 'error')
        toast('任务失败：' + ev.job.error.slice(0, 100), 'err');
    } else if (ev.type === 'log') {
      appendLogLive(ev);
    }
  };
}

function busyJobs() {
  return [...state.jobs.values()].filter(j =>
    j.status === 'running' || j.status === 'queued');
}
function updatePill() {
  const busy = busyJobs();
  const pill = $('#workerPill');
  pill.textContent = busy.length ? `● 合成中 ${busy.length}` : '● 就绪';
  pill.className = 'pill' + (busy.length ? ' busy' : '');
  const btn = $('#genEpisodeBtn');
  if (btn) btn.disabled = busy.length > 0;
  drawProgress();
}

async function onJobDone(jobId) {
  const ctx = state.pending.get(jobId);
  if (!ctx) return;
  state.pending.delete(jobId);
  const j = await api('/api/jobs/' + jobId);
  const r = j.result;
  if (!r) return;
  if (ctx.type === 'seg') {
    const audio = $(`#segAudio${ctx.idx}`);
    if (audio) { audio.src = r.url; audio.hidden = false; }
    toast('✅ 试听片段已生成', 'ok');
  } else if (ctx.type === 'voice') {
    const audio = $(`#vAudio${ctx.uid}`);
    if (audio) { audio.src = r.url; audio.hidden = false; }
  } else if (ctx.type === 'ep') {
    state.lastEpisode = r;
    if (state.view === 'create') renderEpisodeStage();
    toast(`🎉 节目合成完成，时长 ${fmtDur(r.duration)}`, 'ok');
  } else if (ctx.type === 'aiscript') {
    applyAIScript(r);
  }
  loadLibrary();
}

// ── 路由 ─────────────────────────────────────────────
document.addEventListener('click', e => {
  const tab = e.target.closest('.tab');
  if (tab) switchView(tab.dataset.view);
});
function switchView(v) {
  state.view = v;
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.view === v));
  ({ create: renderCreate, voices: renderVoices, library: renderLibrary })[v]();
}

// ── 音色下拉选项（按场景分组，构建一次复用） ─────────
function buildVoiceOpts() {
  const groups = {};
  state.voices.forEach(v => {
    const g = v['推荐场景'] || '其他';
    (groups[g] ??= []).push(v);
  });
  state.voiceOpts = Object.keys(groups).sort().map(g =>
    `<optgroup label="${esc(g)}">` + groups[g].map(v =>
      `<option value="${esc(v.voice_type)}">${esc(v['音色名称'])} · ${esc(v['语种'])}</option>`
    ).join('') + '</optgroup>').join('');
}

// ── 视图 1：播客创作 ─────────────────────────────────
function renderCreate() {
  $('#view').innerHTML = `
  <div class="create-wrap">
    <section class="panel" id="scriptPanel">
      <h3 style="justify-content:space-between">📝 节目脚本
        <button class="btn warm sm" id="aiOpenBtn">🤖 AI 生成对白</button>
      </h3>
      <label class="field" style="margin:0 0 6px">
        <input type="text" id="titleInput" maxlength="60" value="${esc(state.title)}" placeholder="给这期节目起个名字" />
      </label>

      <div class="host-row">
        ${hostSlotHTML(0, 'host-a', '🧔', '主播 A')}
        ${hostSlotHTML(1, 'host-b', '👩', '主播 B')}
      </div>

      <div class="seg-list" id="segList"></div>

      <div class="add-row">
        <button class="btn ghost sm" id="addSegA">＋ 主播A 台词</button>
        <button class="btn ghost sm" id="addSegB">＋ 主播B 台词</button>
      </div>

      <div class="params">
        ${paramHTML('speed', '语速', .8, 1.5, .05)}
        ${paramHTML('volume', '音量', .8, 1.5, .05)}
        ${paramHTML('pitch', '音调', .8, 1.2, .05)}
      </div>

      <div class="add-row">
        <button class="btn ghost sm" id="loadSample">✨ 载入示例脚本</button>
        <button class="btn ghost sm" id="clearAll">🧹 清空重写</button>
      </div>
    </section>

    <div class="stage-wrap">
      <section class="episode-stage" id="episodeStage"></section>
      <div class="stage-actions">
        <button class="btn warm" id="genEpisodeBtn">🚀 生成整期节目</button>
      </div>
      <section class="panel recent">
        <h3>🕐 最近节目</h3>
        <div class="filmstrip" id="recentStrip"></div>
      </section>
    </div>
  </div>`;

  bindCreate();
  renderSegList();
  renderEpisodeStage();
  renderRecent();
}

function hostSlotHTML(i, cls, avatar, label) {
  const cur = state.hosts[i];
  const v = state.vmap.get(cur);
  return `
  <div class="host-slot ${cls}">
    <span class="avatar">${avatar}</span>
    <div style="min-width:0;flex:1">
      <span class="ht">${label}</span>
      <span class="hn">${esc(v ? v['音色名称'] : '未选择')}</span>
    </div>
    <button class="mini-act" data-action="pick-host" data-host="${i}" title="更换">🔄</button>
  </div>`;
}

function paramHTML(key, label, min, max, step) {
  return `
  <div class="param">
    <div class="pl"><span>${label}</span><b id="${key}Val">×${state.params[key].toFixed(2)}</b></div>
    <input type="range" id="${key}Range" min="${min}" max="${max}" step="${step}"
      value="${state.params[key]}" />
  </div>`;
}

function renderSegList() {
  $('#segList').innerHTML = state.segments.map((s, i) => {
    const hostIdx = state.hosts.indexOf(s.voice) === 1 ? 1 : 0;
    return `
    <div class="seg-card ${hostIdx === 1 ? 'active-speaker' : ''}" id="segCard${i}">
      <div class="seg-top">
        <span class="seg-no">${i + 1}</span>
        <select data-idx="${i}" class="seg-voice">${state.voiceOpts}</select>
        <span class="seg-count">${s.text.length}字</span>
        <button class="mini-act" data-action="seg-preview" data-idx="${i}" title="单段试听">▶</button>
        <button class="mini-act" data-action="seg-up" data-idx="${i}" title="上移">▲</button>
        <button class="mini-act" data-action="seg-down" data-idx="${i}" title="下移">▼</button>
        <button class="mini-act" data-action="seg-del" data-idx="${i}" title="删除">✕</button>
      </div>
      <textarea data-idx="${i}" class="seg-text" placeholder="输入这一段要说的话…">${esc(s.text)}</textarea>
      <div class="seg-foot"><audio id="segAudio${i}" controls hidden></audio></div>
    </div>`;
  }).join('');
  $$('.seg-voice').forEach(sel => { sel.value = state.segments[sel.dataset.idx].voice; });
}

function renderEpisodeStage() {
  const el = $('#episodeStage');
  if (!el) return;
  const busy = busyJobs().some(j => state.pending.get(j.id)?.type === 'ep');
  const writingJob = busyJobs().find(j =>
    state.pending.get(j.id)?.type === 'aiscript');
  const r = state.lastEpisode;
  if (writingJob) {
    const topic = writingJob.title.replace(/^AI 编剧：/, '');
    el.innerHTML = `
    <div class="ep-flex">
      <span class="mic-disc busy">🤖</span>
      <div class="ep-info">
        <div class="t">AI 正在创作剧本…</div>
        <div class="s">主题：${esc(topic)} · 通常需要 30~120 秒，完成后自动载入</div>
        <div class="eq run">${'<i></i>'.repeat(11)}</div>
      </div>
    </div>
    <div class="prog indeterminate"><b></b></div>
    <div class="ep-player">
      <div class="empty-mini">✍️ 剧本写完后会自动出现在左侧，点右上角 📜 可查看实时日志</div>
    </div>`;
    return;
  }
  el.innerHTML = `
  <div class="ep-flex">
    <span class="mic-disc${busy ? ' busy' : ''}">${busy ? '⏳' : '🎙'}</span>
    <div class="ep-info">
      <div class="t">${esc(state.title || '未命名节目')}</div>
      <div class="s">共 ${state.segments.filter(s => s.text.trim()).length} 段台词
        ${r ? ` · 成品时长 ${fmtDur(r.duration)}` : busy ? ' · 正在合成，请稍候…' : ' · 尚未生成'}</div>
      <div class="eq ${busy ? 'run' : ''}">${'<i></i>'.repeat(11)}</div>
    </div>
  </div>
  <div class="prog"><b id="epProg"></b></div>
  <div class="ep-player">
    ${r ? `<audio controls src="${r.url}"></audio>
      <div style="margin-top:10px;display:flex;gap:9px">
        <a class="btn warm sm" href="${r.url}" download>⬇ 下载 MP3</a>
      </div>` : '<div class="empty-mini">生成后可在此在线试听与下载 🎧</div>'}
  </div>`;
  drawProgress();
}

function drawProgress() {
  const bar = $('#epProg');
  if (!bar) return;
  const running = busyJobs().find(j => state.pending.get(j.id)?.type === 'ep');
  bar.style.width = ((running ? running.progress : state.lastEpisode ? 1 : 0) * 100) + '%';
}

function renderRecent() {
  const el = $('#recentStrip');
  if (!el) return;
  const eps = state.library.episodes.slice(0, 10);
  if (!eps.length) { el.innerHTML = '<div class="empty-mini">还没有节目，先写点台词吧 ✍️</div>'; return; }
  el.innerHTML = eps.map(e => `
    <div class="rec-cell" data-url="${e.url}">
      <div class="rt">🎧 ${esc(e.name.replace(/\.mp3$/, ''))}</div>
      <div class="rd">${fmtDate(e.mtime)} · ${fmtDur(e.duration)} · ${fmtSize(e.size)}</div>
      <audio controls preload="none" src="${e.url}"></audio>
    </div>`).join('');
}

// ── 创作页事件绑定 ───────────────────────────────────
function bindCreate() {
  $('#titleInput').addEventListener('input', e => { state.title = e.target.value; });
  $('#addSegA').addEventListener('click', () => addSeg(state.hosts[0]));
  $('#addSegB').addEventListener('click', () => addSeg(state.hosts[1]));
  $('#loadSample').addEventListener('click', loadSampleScript);
  $('#clearAll').addEventListener('click', () => {
    state.segments = [{ text: '', voice: state.hosts[0] }];
    renderSegList();
  });
  $('#genEpisodeBtn').addEventListener('click', generateEpisode);
  $('#aiOpenBtn').addEventListener('click', openAIModal);

  $('#scriptPanel').addEventListener('click', e => {
    const b = e.target.closest('[data-action="pick-host"]');
    if (!b) return;
    const hi = +b.dataset.host;
    const slot = b.closest('.host-slot');
    slot.innerHTML = `
      <select class="host-pick" style="flex:1">${state.voiceOpts}</select>
      <button class="mini-act host-ok" title="确定">✓</button>
      <button class="mini-act host-cancel" title="取消">✕</button>`;
    const sel = $('.host-pick', slot);
    sel.value = state.hosts[hi];
    sel.focus();
    const rerenderHosts = () => {
      $('.host-row').innerHTML =
        hostSlotHTML(0, 'host-a', '🧔', '主播 A') +
        hostSlotHTML(1, 'host-b', '👩', '主播 B');
    };
    $('.host-ok', slot).addEventListener('click', () => {
      state.hosts[hi] = sel.value;
      rerenderHosts();
      renderSegList();
      toast('已更换主播，新添加的台词会使用该音色', 'ok');
    });
    $('.host-cancel', slot).addEventListener('click', rerenderHosts);
    sel.addEventListener('keydown', ev => {
      if (ev.key === 'Enter') $('.host-ok', slot).click();
    });
  });

  ['speed', 'volume', 'pitch'].forEach(k => {
    $('#' + k + 'Range').addEventListener('input', e => {
      state.params[k] = parseFloat(e.target.value);
      $('#' + k + 'Val').textContent = '×' + state.params[k].toFixed(2);
    });
  });

  $('#segList').addEventListener('input', e => {
    const ta = e.target.closest('.seg-text');
    if (ta) {
      const i = +ta.dataset.idx;
      state.segments[i].text = ta.value;
      const cnt = $(`#segCard${i} .seg-count`);
      if (cnt) cnt.textContent = ta.value.length + '字';
    }
  });
  $('#segList').addEventListener('change', e => {
    const sel = e.target.closest('.seg-voice');
    if (sel) {
      const i = +sel.dataset.idx;
      state.segments[i].voice = sel.value;
      const card = $('#segCard' + i);
      card.classList.toggle('active-speaker', state.hosts[1] === sel.value);
    }
  });
  $('#segList').addEventListener('click', segCardActions);
}

async function segCardActions(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const i = +btn.dataset.idx;
  const act = btn.dataset.action;
  if (act === 'seg-del') {
    state.segments.splice(i, 1);
    if (!state.segments.length)
      state.segments = [{ text: '', voice: state.hosts[0] }];
    renderSegList();
  } else if (act === 'seg-up' && i > 0) {
    [state.segments[i - 1], state.segments[i]] = [state.segments[i], state.segments[i - 1]];
    renderSegList();
  } else if (act === 'seg-down' && i < state.segments.length - 1) {
    [state.segments[i + 1], state.segments[i]] = [state.segments[i], state.segments[i + 1]];
    renderSegList();
  } else if (act === 'seg-preview') {
    const s = state.segments[i];
    if (!s.text.trim()) return toast('这一段还是空的', 'err');
    submitPreview(s, { type: 'seg', idx: i });
  }
}

function addSeg(voice) {
  state.segments.push({ text: '', voice });
  renderSegList();
  const cards = $$('.seg-card');
  cards[cards.length - 1]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('#segList .seg-card:last-child textarea')?.focus();
}

// ── 试听 / 节目任务提交 ──────────────────────────────
async function submitPreview(s, ctx) {
  if (busyJobs().length) return toast('请等当前任务完成', 'err');
  const body = {
    text: s.text, voice: s.voice,
    speed: state.params.speed, volume: state.params.volume, pitch: state.params.pitch,
  };
  const j = await api('/api/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  state.pending.set(j.id, ctx);
  state.logJobId = j.id;
}

async function generateEpisode() {
  const segs = state.segments.filter(s => s.text.trim());
  if (!segs.length) return toast('先写点台词吧', 'err');
  if (segs.some(s => !s.voice)) return toast('有段落没选音色', 'err');
  const body = {
    title: state.title,
    segments: segs.map(s => ({
      text: s.text, voice: s.voice,
      speed: state.params.speed, volume: state.params.volume, pitch: state.params.pitch,
    })),
  };
  const j = await api('/api/episode', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  state.pending.set(j.id, { type: 'ep' });
  state.logJobId = j.id;
  state.lastEpisode = null;
  renderEpisodeStage();
}

// ── 示例脚本 ─────────────────────────────────────────
function loadSampleScript() {
  const A = state.hosts[0], B = state.hosts[1];
  state.title = 'AI 那些事儿 · 第 1 期';
  state.segments = [
    { voice: A, text: '大家好，欢迎收听《AI 那些事儿》，我是主播。每周和你聊一个和人工智能有关的有趣话题。' },
    { voice: B, text: '大家好呀，我是今天的嘉宾。最近有个词特别火，叫 AI Agent，也就是智能代理。它到底是什么呢？' },
    { voice: A, text: '简单来说，它是一个能听懂你的要求、自己动手完成任务的 AI。你只需要说一句话，它就能帮你查资料、写文档、剪视频，甚至安排好一天的日程。' },
    { voice: B, text: '听起来就像有了一个不知疲倦的助理。那普通人现在能用起来吗？' },
    { voice: A, text: '当然可以。现在的工具已经越来越简单，打开网页、选一个喜欢的声音，就能做出属于你自己的播客节目。' },
    { voice: B, text: '没错，就像我们现在这期节目一样。好了，今天就聊到这里，我们下期再见！' },
  ];
  renderSegList();
  const ti = $('#titleInput');
  if (ti) ti.value = state.title;
  toast('已载入示例，点击右侧「生成整期节目」试试', 'ok');
}

// ── AI 编剧弹窗 ─────────────────────────────────────
async function openAIModal() {
  const m = $('#aiModal');
  m.hidden = false;
  $('#aiTopic').focus();
  syncAIModalSegs();
  if (!state.ai.loaded) {
    const d = await api('/api/ai-styles');
    state.ai.styles = d.styles;
    state.ai.loaded = true;
  }
  renderAIStyleChips();
}

function closeAIModal() {
  $('#aiModal').hidden = true;
}

function syncAIModalSegs() {
  $$('#aiModeSeg button').forEach(b =>
    b.classList.toggle('active', b.dataset.mode === state.ai.mode));
  $$('#aiTurnSeg button').forEach(b =>
    b.classList.toggle('active', +b.dataset.turns === state.ai.turns));
}

function renderAIStyleChips() {
  $('#aiStyleChips').innerHTML = state.ai.styles.map(s =>
    `<button class="chip ${state.ai.style === s.id ? 'on' : ''}"
      data-style="${s.id}">${esc(s.label)}</button>`).join('');
}

$('#aiClose').addEventListener('click', closeAIModal);
$('#aiCancel').addEventListener('click', closeAIModal);
$('#aiModal').addEventListener('click', e => {
  if (e.target.id === 'aiModal') closeAIModal();
});
$('#aiModeSeg').addEventListener('click', e => {
  const b = e.target.closest('[data-mode]');
  if (b) { state.ai.mode = b.dataset.mode; syncAIModalSegs(); }
});
$('#aiTurnSeg').addEventListener('click', e => {
  const b = e.target.closest('[data-turns]');
  if (b) { state.ai.turns = +b.dataset.turns; syncAIModalSegs(); }
});
$('#aiStyleChips').addEventListener('click', e => {
  const b = e.target.closest('[data-style]');
  if (b) { state.ai.style = b.dataset.style; renderAIStyleChips(); }
});

$('#aiSubmit').addEventListener('click', async () => {
  const topic = $('#aiTopic').value.trim();
  if (!topic) return toast('先输入一个主题', 'err');
  if (busyJobs().length) return toast('请等当前任务完成', 'err');
  const btn = $('#aiSubmit');
  btn.disabled = true;
  btn.textContent = '🤖 创作中，约需 30~120 秒…';
  try {
    const j = await api('/api/ai-script', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic, style: state.ai.style,
        turns: state.ai.turns, mode: state.ai.mode,
      }),
    });
    state.pending.set(j.id, { type: 'aiscript' });
    state.logJobId = j.id;
    closeAIModal();
    toast('🤖 AI 正在写稿，完成后自动载入脚本');
  } catch (e) {
    toast(e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ 生成对白';
  }
});

function applyAIScript(r) {
  const voiceOf = sp => state.hosts[sp === 'B' ? 1 : 0];
  state.title = r.title || state.title;
  state.segments = r.segments.map(s => ({
    text: s.text,
    voice: voiceOf(s.speaker),
  }));
  state.lastEpisode = null;
  if (state.view === 'create') {
    const ti = $('#titleInput');
    if (ti) ti.value = state.title;
    renderSegList();
    renderEpisodeStage();
  }
  toast(`✅ AI 剧本已载入：《${r.title}》，可直接生成节目`, 'ok');
}

// ── 视图 2：音色库 ───────────────────────────────────
const LANG_FILTERS = ['全部', '中文', '英文', '中/英'];

function renderVoices() {
  const scenes = ['全部', ...new Set(state.voices.map(v => v['推荐场景']))];
  $('#view').innerHTML = `
  <div class="sample-row">
    <span class="muted" style="font-size:12.5px;white-space:nowrap">🔖 试听文本</span>
    <input type="text" id="sampleInput" value="${esc(state.sampleText)}" maxlength="200" />
  </div>
  <div class="toolbar">
    <input type="text" id="voiceSearch" placeholder="搜索音色名称，如：播客 / 姐姐 / 英语…" value="${esc(state.vq)}" />
    <div class="chips" id="langChips">
      ${LANG_FILTERS.map(l =>
        `<button class="chip v ${state.vlang === l ? 'on' : ''}" data-lang="${l}">${l}</button>`).join('')}
    </div>
    <span class="count" id="voiceCount"></span>
  </div>
  <div class="toolbar" style="margin-top:-6px">
    <div class="chips" id="sceneChips">
      ${scenes.map(s =>
        `<button class="chip ${state.vscene === s ? 'on' : ''}" data-scene="${esc(s)}">${esc(s)}</button>`).join('')}
    </div>
  </div>
  <div class="voice-grid" id="voiceGrid"></div>`;

  $('#sampleInput').addEventListener('input', e => state.sampleText = e.target.value);
  $('#voiceSearch').addEventListener('input', e => { state.vq = e.target.value; drawVoiceGrid(); });
  $('#langChips').addEventListener('click', e => {
    const c = e.target.closest('[data-lang]');
    if (c) { state.vlang = c.dataset.lang; renderVoices(); $('#voiceSearch').focus(); }
  });
  $('#sceneChips').addEventListener('click', e => {
    const c = e.target.closest('[data-scene]');
    if (c) { state.vscene = c.dataset.scene; renderVoices(); }
  });
  $('#voiceGrid').addEventListener('click', voiceGridActions);
  drawVoiceGrid();
}

function filteredVoices() {
  const q = state.vq.trim().toLowerCase();
  return state.voices.filter(v => {
    if (state.vlang !== '全部') {
      if (state.vlang === '中文' && !v['语种'].includes('中')) return false;
      if (state.vlang === '英文' && !v['语种'].includes('英')) return false;
      if (state.vlang === '中/英' && v['语种'] !== '中/英') return false;
    }
    if (state.vscene !== '全部' && v['推荐场景'] !== state.vscene) return false;
    if (q && !(`${v['音色名称']} ${v.voice_type}`.toLowerCase().includes(q))) return false;
    return true;
  });
}

function drawVoiceGrid() {
  const list = filteredVoices();
  const grid = $('#voiceGrid');
  if (!grid) return;
  $('#voiceCount').textContent = `${list.length} / ${state.voices.length} 个音色`;
  if (!list.length) {
    grid.innerHTML = '<div class="empty-gal"><span class="big">🔍</span>没有匹配的音色</div>';
    return;
  }
  grid.innerHTML = list.map(v => {
    const uid = v.voice_type.replace(/[^a-zA-Z0-9]/g, '').slice(-12);
    const isA = state.hosts[0] === v.voice_type;
    const isB = state.hosts[1] === v.voice_type;
    return `
    <div class="voice-card">
      <div class="vc-head">
        <span class="vc-avatar">${v.voice_type.startsWith('zh_male') || v.voice_type.includes('_male_') ? '🧔' : '👩'}</span>
        <div>
          <div class="vc-name">${esc(v['音色名称'])}</div>
          <div class="badges" style="margin-top:3px">
            <span class="badge lang">${esc(v['语种'])}</span>
            <span class="badge">${esc(v['推荐场景'])}</span>
            ${isA ? '<span class="badge lang">主播A</span>' : ''}
            ${isB ? '<span class="badge lang">主播B</span>' : ''}
          </div>
        </div>
      </div>
      <audio id="vAudio${uid}" controls hidden></audio>
      <div class="vc-acts">
        <button class="btn ghost sm" data-action="voice-preview" data-uid="${uid}" data-voice="${esc(v.voice_type)}">▶ 试听</button>
        <button class="btn primary sm" data-action="voice-use" data-voice="${esc(v.voice_type)}">✍ 用它创作</button>
      </div>
    </div>`;
  }).join('');
}

async function voiceGridActions(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const voice = btn.dataset.voice;
  if (btn.dataset.action === 'voice-preview') {
    if (!state.sampleText.trim()) return toast('试听文本为空', 'err');
    if (busyJobs().length) return toast('请等当前任务完成', 'err');
    const j = await api('/api/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: state.sampleText, voice }),
    });
    state.pending.set(j.id, { type: 'voice', uid: btn.dataset.uid });
    state.logJobId = j.id;
    toast('🎧 试听合成中…');
  } else if (btn.dataset.action === 'voice-use') {
    state.segments.push({ text: '', voice });
    switchView('create');
    const cards = $$('.seg-card');
    cards[cards.length - 1]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    $('#segList .seg-card:last-child textarea')?.focus();
  }
}

// ── 视图 3：音频库 ───────────────────────────────────
function renderLibrary() {
  $('#view').innerHTML = `
  <div class="lib-wrap">
    <div class="lib-tabs">
      <button data-lib="episodes" class="${state.libTab === 'episodes' ? 'active' : ''}">🎧 完整节目 (${state.library.episodes.length})</button>
      <button data-lib="clips" class="${state.libTab === 'clips' ? 'active' : ''}">🎵 单段片段 (${state.library.clips.length})</button>
    </div>
    <div class="lib-grid" id="libGrid"></div>
  </div>`;
  $$('.lib-tabs button').forEach(b => b.addEventListener('click', () => {
    state.libTab = b.dataset.lib;
    renderLibrary();
  }));
  $('#libGrid').addEventListener('click', async e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    if (btn.dataset.action === 'del') {
      await api('/api/delete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: state.libTab, name: btn.dataset.name }),
      });
      toast('已删除', 'ok');
      await loadLibrary();
      drawLibGrid();
    }
  });
  drawLibGrid();
}

function drawLibGrid() {
  const grid = $('#libGrid');
  const items = state.library[state.libTab];
  if (!items.length) {
    grid.innerHTML = `<div class="empty-gal"><span class="big">${state.libTab === 'episodes' ? '🎙' : '🎵'}</span>
      还没有${state.libTab === 'episodes' ? '节目' : '片段'}</div>`;
    return;
  }
  grid.innerHTML = items.map(it => `
    <div class="lib-card">
      <div class="lt">
        <span class="lic">${state.libTab === 'episodes' ? '🎧' : '🎵'}</span>
        <div>
          <div class="ln">${esc(it.name)}</div>
          <div class="ls">${fmtDate(it.mtime)} · ${fmtDur(it.duration)} · ${fmtSize(it.size)}</div>
        </div>
      </div>
      <audio controls preload="none" src="${it.url}"></audio>
      <div class="acts">
        <a class="btn warm sm" href="${it.url}" download>⬇ 下载</a>
        <button class="btn ghost sm" data-action="del" data-name="${esc(it.name)}">🗑 删除</button>
      </div>
    </div>`).join('');
}

// ── 音频库数据 ───────────────────────────────────────
async function loadLibrary() {
  state.library = await api('/api/library');
  if (state.view === 'library') drawLibGrid();
  if (state.view === 'create') renderRecent();
}

// ── 日志抽屉 ─────────────────────────────────────────
function appendLogLive(ev) {
  if (ev.job_id !== state.logJobId) return;
  const body = $('#logBody');
  if (body && !body.hidden) body.textContent += ev.line.msg + '\n';
}
$('#logBtn').addEventListener('click', async () => {
  const d = $('#logDrawer');
  d.hidden = !d.hidden;
  if (!d.hidden && state.logJobId) {
    const j = await api('/api/jobs/' + state.logJobId).catch(() => null);
    if (j) $('#logBody').textContent = j.logs.map(l => l.msg).join('\n');
  }
});
$('#logClose').addEventListener('click', () => { $('#logDrawer').hidden = true; });

// ── 启动 ─────────────────────────────────────────────
(async function init() {
  const h = await api('/api/health');
  if (!h.tts_configured)
    toast('⚠ TTS API 未配置，请检查 .env 中 TTS_* 变量', 'err');
  const data = await api('/api/voices');
  state.voices = data.voices;
  state.voices.forEach(v => state.vmap.set(v.voice_type, v));
  buildVoiceOpts();
  connectSSE();
  renderCreate();
  loadLibrary();
})();
