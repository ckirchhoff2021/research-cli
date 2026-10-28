"""Drama Studio FastAPI 服务：项目管理 + 细粒度编辑 + 任务提交 + SSE 事件 + 媒体服务。"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import jobs, pipeline

app = FastAPI(title="Drama Studio", docs_url="/api/docs")

MEDIA_ROOT = pipeline.OUTPUTS_DIR.resolve()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.on_event("startup")
async def _bind_loop() -> None:
    jobs.bus.bind_loop(asyncio.get_running_loop())


# ── 媒体 URL 归一化：本地绝对路径 → /media/... ─────────
def _media_url(value: str) -> str:
    if not value or not isinstance(value, str) or not value.startswith("/"):
        return value
    p = Path(value).resolve()
    try:
        rel = p.relative_to(MEDIA_ROOT)
    except Exception:
        return value
    url = "/media/" + str(rel)
    # 带文件修改时间版本号：重新生成同名文件后浏览器能立刻拿到新图
    try:
        url += f"?v={int(p.stat().st_mtime * 1000)}"
    except OSError:
        pass
    return url


_PATH_FIELDS = {"ref_image", "video_file", "final_video", "voice_file"}


def to_dto(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _PATH_FIELDS and isinstance(v, str):
                out[k] = _media_url(v)
            else:
                out[k] = to_dto(v)
        return out
    if isinstance(obj, list):
        return [to_dto(v) for v in obj]
    return obj


def _guard(project_id: str) -> None:
    if jobs.has_running(project_id):
        raise HTTPException(status_code=409, detail="该项目有任务正在执行，请等待完成后再编辑")


# ── 基础接口 ──────────────────────────────────────────
@app.middleware("http")
async def _no_cache_html(request, call_next):
    """HTML 入口不缓存，确保版本号/页面更新立即生效。"""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/doctor")
def doctor():
    s = pipeline.get_settings()
    ff = pipeline.find_ffmpeg()
    return {
        "ffmpeg": bool(ff),
        "ark_api_key": bool(s["ark_api_key"]),
        "llm_model": s["llm_model"],
        "video_model": s["video_model"],
        "image_model": s["image_model"],
        "tts_configured": bool(s["tts_access_token"]),
        "outputs_dir": str(pipeline.OUTPUTS_DIR),
    }


@app.get("/api/voices")
def voice_catalog():
    """可用音色（去重），供角色编辑时的 datalist。"""
    sys.path.insert(0, str(pipeline.SKILL_SCRIPTS))
    from creative import VOICE_MAP
    seen: dict[str, str] = {}
    for label, vid in VOICE_MAP.items():
        seen.setdefault(vid, label)
    return [{"id": vid, "label": label} for vid, label in seen.items()]


# ── 项目列表/详情 ─────────────────────────────────────
@app.get("/api/projects")
def get_projects():
    return [to_dto(p) for p in pipeline.list_projects()]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    try:
        return to_dto(pipeline.load(project_id))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 新建项目（异步任务） ──────────────────────────────
class CreateProjectBody(BaseModel):
    concept: str = Field(min_length=2)
    shots: int = 7
    ratio: str = "16:9"
    resolution: str = "1080p"
    style: str = "gufeng"


@app.post("/api/projects")
def create_project(body: CreateProjectBody):
    payload = body.model_dump()
    job = jobs.submit(
        "create_project", f"创作：{body.concept[:24]}",
        lambda j, log: pipeline.create_project(payload, log),
    )
    return jobs.job_snapshot(job)


# ── 人工编辑：剧本元信息 ──────────────────────────────
class ScriptBody(BaseModel):
    title: str | None = None
    genre: str | None = None
    logline: str | None = None
    theme: str | None = None
    style_anchor: str | None = None
    bgm_style: str | None = None


@app.put("/api/projects/{project_id}/script")
def edit_script(project_id: str, body: ScriptBody):
    _guard(project_id)
    p = pipeline.load(project_id)
    for k, v in body.model_dump(exclude_none=True).items():
        p["script"][k] = v
    pipeline.save(p)
    return to_dto(p)


# ── 人工编辑：角色 ───────────────────────────────────
class CharacterBody(BaseModel):
    role: str | None = None
    appearance: str | None = None
    tag: str | None = None
    voice_type: str | None = None


@app.put("/api/projects/{project_id}/characters/{name}")
def edit_character(project_id: str, name: str, body: CharacterBody):
    _guard(project_id)
    p = pipeline.load(project_id)
    char = next((c for c in p["script"]["characters"] if c["name"] == name), None)
    if char is None:
        raise HTTPException(404, "角色不存在")
    char.update(body.model_dump(exclude_none=True))
    # 外观变化会影响每个镜头 prompt
    pipeline.rebuild_prompts(p)
    pipeline.save(p)
    return to_dto(p)


# ── 人工编辑：分镜 ───────────────────────────────────
class DialogueBody(BaseModel):
    character: str = ""
    text: str = ""
    start_offset: float = 2.5


class ShotBody(BaseModel):
    title: str | None = None
    scene: str | None = None
    action: str | None = None
    emotion: str | None = None
    duration: int | None = None
    characters: list[str] | None = None
    dialogues: list[DialogueBody] | None = None


@app.put("/api/projects/{project_id}/shots/{index}")
def edit_shot(project_id: str, index: int, body: ShotBody):
    _guard(project_id)
    p = pipeline.load(project_id)
    if not 1 <= index <= len(p["shots"]):
        raise HTTPException(404, "镜头不存在")
    shot = p["shots"][index - 1]
    data = body.model_dump(exclude_none=True)
    if "dialogues" in data:
        data["dialogues"] = [d if isinstance(d, dict) else d.model_dump()
                             for d in data["dialogues"]]
    shot.update(data)
    # 对白改了，旧的 voice 条目视为过期
    if "dialogues" in data:
        shot["voices"] = []
    pipeline.rebuild_prompts(p)
    pipeline.save(p)
    return to_dto(p)


class AddShotBody(BaseModel):
    title: str = "新增镜头"
    scene: str = ""
    action: str = ""
    emotion: str = "自然"
    characters: list[str] = []
    dialogues: list[dict] = []
    duration: int = 10


@app.post("/api/projects/{project_id}/shots")
def add_shot(project_id: str, body: AddShotBody):
    _guard(project_id)
    p = pipeline.load(project_id)
    shot = body.model_dump()
    shot.update({"index": len(p["shots"]) + 1,
                 "uid": "shot_" + uuid.uuid4().hex[:10],
                 "prompt": "", "video_file": "",
                 "voices": [], "status": "pending", "error": ""})
    p["shots"].append(shot)
    p["num_shots"] = len(p["shots"])
    pipeline.rebuild_prompts(p)
    pipeline.save(p)
    return to_dto(p)


@app.delete("/api/projects/{project_id}/shots/{index}")
def delete_shot(project_id: str, index: int):
    _guard(project_id)
    p = pipeline.load(project_id)
    if not 1 <= index <= len(p["shots"]):
        raise HTTPException(404, "镜头不存在")
    p["shots"].pop(index - 1)
    for i, s in enumerate(p["shots"]):
        s["index"] = i + 1
    p["num_shots"] = len(p["shots"])
    pipeline.rebuild_prompts(p)
    pipeline.save(p)
    return to_dto(p)


# ── AI 生成单个镜头（不落盘，前端确认后再追加） ─────
class GenerateShotBody(BaseModel):
    prompt: str = Field(min_length=2, max_length=500)


@app.post("/api/projects/{project_id}/shots/generate")
def generate_shot(project_id: str, body: GenerateShotBody):
    _guard(project_id)
    p = pipeline.load(project_id)
    try:
        shot = pipeline.generate_shot(p, body.prompt)
    except Exception as e:  # LLM/JSON 解析失败统一 502
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{e}") from e
    return to_dto(shot)


# ── 镜头拖拽排序 ─────────────────────────────────────
class ReorderShotsBody(BaseModel):
    order: list[int]


@app.post("/api/projects/{project_id}/shots/reorder")
def reorder_shots(project_id: str, body: ReorderShotsBody):
    _guard(project_id)
    p = pipeline.load(project_id)
    try:
        pipeline.reorder_shots(p, body.order)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    pipeline.save(p)
    return to_dto(p)


# ── 任务触发 ─────────────────────────────────────────
class JobBody(BaseModel):
    kind: str
    options: dict = {}


@app.post("/api/projects/{project_id}/jobs")
def trigger_job(project_id: str, body: JobBody):
    try:
        pipeline.load(project_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    if jobs.has_running(project_id):
        raise HTTPException(409, "该项目已有任务在执行")

    kind = body.kind
    opts = body.options
    feedback = (opts.get("feedback") or "").strip()

    def _load():
        return pipeline.load(project_id)

    if kind == "char_image":
        name = opts.get("name", "")
        fn = lambda j, log: pipeline.gen_character_image(_load(), name, log, feedback=feedback)
        title = f"定妆照：{name}"
    elif kind == "voices":
        voice_sel = (opts.get("voice_type") or "").strip()
        if opts.get("scope") == "shot":
            si = int(opts["shot"]) - 1
            fn = lambda j, log: pipeline.gen_shot_voices(
                _load(), si, log, feedback=feedback, voice_override=voice_sel)
            title = f"配音：镜头{opts['shot']:02d}"
        else:
            fn = lambda j, log: pipeline.gen_all_voices(
                _load(), log, feedback=feedback, voice_override=voice_sel)
            title = "生成全部配音"
    elif kind == "video":
        force = bool(opts.get("force"))
        if opts.get("scope") == "shot":
            si = int(opts["shot"]) - 1
            fn = lambda j, log: pipeline.gen_shot_video(_load(), si, log, force=force, feedback=feedback)
            title = f"视频：镜头{opts['shot']:02d}"
        else:
            fn = lambda j, log: pipeline.gen_all_videos(_load(), log, force=force, feedback=feedback)
            title = "生成全部视频片段"
    elif kind == "compose":
        fn = lambda j, log: pipeline.compose(_load(), log)
        title = "合成成片"
    elif kind == "run_remaining":
        fn = lambda j, log: pipeline.run_remaining(_load(), log)
        title = "一键补齐并合成"
    elif kind == "regenerate_script":
        fn = lambda j, log: pipeline.regenerate_script(_load(), log, feedback=feedback)
        title = "AI 重新生成剧本"
    else:
        raise HTTPException(400, f"未知任务类型: {kind}")

    job = jobs.submit(kind, title, fn, project_id=project_id)
    return jobs.job_snapshot(job)


# ── 任务查询 / SSE ───────────────────────────────────
@app.get("/api/jobs")
def list_jobs(project_id: str | None = None):
    out = [jobs.job_snapshot(j) for j in jobs.JOBS.values()]
    if project_id:
        out = [j for j in out if j["project_id"] == project_id]
    return list(reversed(out))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    j = jobs.JOBS.get(job_id)
    if j is None:
        raise HTTPException(404, "任务不存在")
    snap = jobs.job_snapshot(j)
    snap["logs"] = j.logs[-300:]
    return snap


@app.get("/api/events")
async def events(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    jobs.bus.subscribers.add(q)

    async def stream():
        # 连接建立时先推一份当前活跃任务快照
        yield _sse({"type": "hello", "jobs": [
            jobs.job_snapshot(j) for j in jobs.JOBS.values()
            if j.status in ("queued", "running")
        ]})
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(q.get(), timeout=20)
                yield _sse(event)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
        jobs.bus.subscribers.discard(q)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 静态资源（媒体 + 前端） ───────────────────────────
app.mount("/media", StaticFiles(directory=str(pipeline.OUTPUTS_DIR)), name="media")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
