"""Image Studio FastAPI 服务：上传 / AI 生成任务 / 编辑保存 / 图库 / SSE / 静态资源。"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs, pipeline

app = FastAPI(title="Image Studio API", docs_url="/api/docs")
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
    return {"ok": True}


def _resolve_image(name: str) -> str:
    """只允许引用工作区三个目录内的文件名，防止路径穿越。"""
    p = Path(name)
    if p.name != name or p.suffix.lower() not in pipeline.IMG_EXTS:
        raise HTTPException(400, f"非法的图片名: {name}")
    for d in pipeline.DIR_MAP.values():
        cand = d / name
        if cand.exists():
            return str(cand)
    raise HTTPException(404, f"图片不存在: {name}")


# ── 上传 ─────────────────────────────────────────────
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 20MB")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(400, "只能上传图片文件")
    path = pipeline.save_upload(data, file.filename or "img.jpg")
    return {"name": Path(path).name, "url": f"/media/uploads/{Path(path).name}"}


# ── 任务 ─────────────────────────────────────────────
class JobBody(BaseModel):
    kind: str
    options: dict = {}


@app.post("/api/jobs")
def trigger(body: JobBody):
    opts = body.options
    if body.kind != "generate":
        raise HTTPException(400, f"未知任务类型: {body.kind}")
    def _as_str(v):
        return v.strip() if isinstance(v, str) else ""
    prompt = _as_str(opts.get("prompt"))
    mode = opts.get("mode") if isinstance(opts.get("mode"), str) else "text2image"
    size = opts.get("size") if isinstance(opts.get("size"), str) else "2K"
    feedback = _as_str(opts.get("feedback"))
    image_names = opts.get("images") or []
    transfer_mode = _as_str(opts.get("transfer_mode")) or "style"
    try:
        strength = int(opts.get("strength", 70))
    except (TypeError, ValueError):
        strength = 70
    if mode == "transfer":
        target_name = _as_str(opts.get("target"))
        if not target_name:
            raise HTTPException(400, "参考迁移需要一张目标图")
        if not image_names:
            raise HTTPException(400, "参考迁移至少需要一张参考图")
        target_path = _resolve_image(target_name)
        ref_paths = [_resolve_image(n) for n in image_names]
    else:
        target_path, ref_paths = "", []
    image_paths = [_resolve_image(n) for n in image_names]
    if not prompt and mode != "transfer":
        raise HTTPException(400, "提示词不能为空")
    if mode in ("edit", "style") and not image_paths:
        raise HTTPException(400, "该模式至少需要一张参考图，请先上传")
    if size not in ("2K", "3K", "4K"):
        raise HTTPException(400, "尺寸只支持 2K / 3K / 4K")
    if mode not in ("text2image", "edit", "style", "transfer"):
        raise HTTPException(400, f"未知模式: {mode}")

    def fn(j, log):
        if mode == "transfer":
            out = pipeline.transfer_image(prompt, target_path, ref_paths,
                                          transfer_mode, strength, size, feedback, log)
        else:
            out = pipeline.generate_image(prompt, image_paths, size, mode, feedback, log)
        return {"name": Path(out).name, "url": f"/media/generated/{Path(out).name}"}

    title = {"text2image": "文生图", "edit": "图像编辑", "style": "风格迁移",
             "transfer": "参考迁移"}.get(mode, "图像生成")
    job = jobs.submit("generate", title, fn)
    return jobs.job_snapshot(job)


# ── 编辑器保存 ───────────────────────────────────────
class EditBody(BaseModel):
    data_url: str


@app.post("/api/save-edit")
def save_edit(body: EditBody):
    s = body.data_url
    if "," not in s or ";" not in s:
        raise HTTPException(400, "data_url 格式不正确")
    head, b64 = s.split(",", 1)
    ext = "png" if "png" in head else "jpg"
    try:
        data = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "图片解码失败")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "图片过大")
    path = pipeline.save_edit(data, ext)
    return {"name": Path(path).name, "url": f"/media/edits/{Path(path).name}"}


# ── AI 局部重绘 ──────────────────────────────────────
class InpaintBody(BaseModel):
    image: str
    box: dict = {}
    prompt: str = ""


@app.post("/api/inpaint")
def inpaint_job(body: InpaintBody):
    s = body.image
    if "," not in s or ";" not in s:
        raise HTTPException(400, "image data_url 格式不正确")
    head, b64 = s.split(",", 1)
    try:
        data = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "图片解码失败")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "图片过大")
    box = body.box if isinstance(body.box, dict) else {}
    for k in ("x", "y", "w", "h"):
        if k not in box:
            raise HTTPException(400, f"缺少选区坐标 {k}")
    prompt = body.prompt if isinstance(body.prompt, str) else ""

    def fn(j, log):
        out = pipeline.inpaint(data, box, prompt, log)
        return {"name": Path(out).name, "url": f"/media/generated/{Path(out).name}"}

    job = jobs.submit("generate", "AI局部重绘", fn)
    return jobs.job_snapshot(job)


# ── 图库 / 任务查询 / SSE ────────────────────────────
@app.get("/api/gallery")
def get_gallery():
    return pipeline.gallery()


@app.get("/api/jobs")
def list_jobs():
    return [jobs.job_snapshot(j) for j in sorted(jobs.JOBS.values(),
                                                  key=lambda x: x.created_at, reverse=True)[:50]]


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
    from fastapi.responses import StreamingResponse

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

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.on_event("startup")
def _startup():
    import asyncio as _a
    jobs.bus.bind_loop(_a.get_running_loop())


# ── 媒体与静态资源（挂载在最后） ─────────────────────
app.mount("/media", StaticFiles(directory=str(pipeline.WORKSPACE)), name="media")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
