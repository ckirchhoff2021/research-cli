"""Podcast Studio FastAPI 服务：音色库 / 单段试听 / 整期合成 / 音频库 / SSE。"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs, pipeline
from . import aiwriter

app = FastAPI(title="Podcast Studio API", docs_url="/api/docs")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.middleware("http")
async def _no_cache_html(request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p.endswith((".html", ".js", ".css")):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


@app.get("/api/health")
def health():
    return {"ok": True, "tts_configured": pipeline.tts_configured()}


# ── 音色库 ───────────────────────────────────────────
@app.get("/api/voices")
def voices():
    return {"voices": pipeline.load_voices()}


# ── AI 编剧 ──────────────────────────────────────────
@app.get("/api/ai-styles")
def ai_styles():
    return {"styles": [{"id": k, "label": v["label"]}
                       for k, v in aiwriter.STYLES.items()]}


class AIScriptBody(BaseModel):
    topic: str
    style: str = "chat"
    turns: int = 12
    mode: str = "dialogue"


@app.post("/api/ai-script")
def ai_script(body: AIScriptBody):
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(400, "请先输入节目主题")
    try:
        turns = int(body.turns)
    except (TypeError, ValueError):
        turns = 12
    style = body.style if body.style in aiwriter.STYLES else "chat"
    mode = body.mode if body.mode in ("dialogue", "monologue") else "dialogue"

    def fn(j, log):
        return aiwriter.generate_dialogue(topic, style, turns, mode, log)

    job = jobs.submit("aiscript", f"AI 编剧：{topic[:20]}", fn)
    return jobs.job_snapshot(job)


# ── 单段试听 ─────────────────────────────────────────
class ClipBody(BaseModel):
    text: str
    voice: str
    speed: float = 1.0
    volume: float = 1.0
    pitch: float = 1.0


def _clamp(v: float, lo: float, hi: float, default: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


@app.post("/api/preview")
def preview(body: ClipBody):
    text = (body.text or "").strip()
    voice = (body.voice or "").strip()
    if not text:
        raise HTTPException(400, "文本不能为空")
    if not voice:
        raise HTTPException(400, "请先选择音色")
    if len(text) > 5000:
        raise HTTPException(400, "单段试听请控制在 5000 字以内")
    speed = _clamp(body.speed, 0.8, 1.5, 1.0)
    volume = _clamp(body.volume, 0.8, 1.5, 1.0)
    pitch = _clamp(body.pitch, 0.8, 1.2, 1.0)

    def fn(j, log):
        return pipeline.save_clip(text, voice, speed_ratio=speed,
                                  volume_ratio=volume, pitch_ratio=pitch,
                                  log=log)

    job = jobs.submit("preview", "单段试听", fn)
    return jobs.job_snapshot(job)


# ── 整期节目 ─────────────────────────────────────────
class Segment(BaseModel):
    text: str = ""
    voice: str = ""


class EpisodeBody(BaseModel):
    title: str = "未命名节目"
    segments: list[Segment] = []


@app.post("/api/episode")
def episode(body: EpisodeBody):
    title = (body.title or "未命名节目").strip()[:60]
    segments = [s.model_dump() for s in body.segments]
    if not segments:
        raise HTTPException(400, "请至少添加一段台词")
    if len(segments) > 100:
        raise HTTPException(400, "单期节目不能超过 100 段")

    def fn(j, log):
        def set_progress(p):
            j.progress = p
            jobs.emit_job(j)

        return pipeline.build_episode(title, segments, log, set_progress)

    job = jobs.submit("episode", f"合成节目：{title}", fn)
    return jobs.job_snapshot(job)


# ── 音频库 ───────────────────────────────────────────
@app.get("/api/library")
def get_library():
    return pipeline.library()


class DeleteBody(BaseModel):
    kind: str
    name: str


@app.post("/api/delete")
def delete(body: DeleteBody):
    try:
        pipeline.delete_media(body.kind, body.name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ── 任务查询 / SSE ───────────────────────────────────
@app.get("/api/jobs")
def list_jobs():
    return [jobs.job_snapshot(j) for j in sorted(
        jobs.JOBS.values(), key=lambda x: x.created_at, reverse=True)[:50]]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    j = jobs.JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    snap = jobs.job_snapshot(j)
    snap["logs"] = j.logs
    snap["result"] = getattr(j, "result", None)
    return snap


@app.get("/api/events")
async def events():
    async def stream():
        q: jobs.asyncio.Queue = jobs.asyncio.Queue()
        jobs.bus.subscribers.add(q)
        try:
            hello = {"type": "hello",
                     "jobs": [jobs.job_snapshot(x) for x in jobs.JOBS.values()]}
            yield f"data: {json.dumps(hello, ensure_ascii=False)}\n\n"
            while True:
                ev = await q.get()
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            jobs.bus.subscribers.discard(q)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.on_event("startup")
def _startup():
    import asyncio as _a
    jobs.bus.bind_loop(_a.get_running_loop())


# ── 媒体与静态资源（挂载在最后） ─────────────────────
app.mount("/media", StaticFiles(directory=str(pipeline.WORKSPACE)),
          name="media")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True),
          name="static")
