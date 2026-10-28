"""全局串行任务队列 + 事件总线（供前端 SSE 实时订阅）。

所有重任务（LLM/TTS/视频生成/ffmpeg）都在唯一 worker 线程中串行执行，
既避免底层 "取最新输出文件" 逻辑产生竞态，也便于人工逐步干预。
"""
from __future__ import annotations

import asyncio
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    title: str
    project_id: str = ""
    status: str = "queued"  # queued | running | done | error
    logs: list[dict] = field(default_factory=list)
    error: str = ""
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    progress: float = 0.0


class EventBus:
    """跨线程向所有 SSE 订阅者广播事件。"""

    def __init__(self) -> None:
        self.subscribers: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def emit(self, event: dict) -> None:
        if self.loop is None:
            return
        for q in tuple(self.subscribers):
            # put 是协程，跨线程投递必须用 put_nowait
            self.loop.call_soon_threadsafe(q.put_nowait, event)


bus = EventBus()

JOBS: dict[str, Job] = {}
_Q: queue.Queue[tuple[Job, Callable]] = queue.Queue()


def job_snapshot(job: Job) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "title": job.title,
        "project_id": job.project_id,
        "status": job.status,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "progress": job.progress,
    }


def emit_job(job: Job) -> None:
    bus.emit({"type": "job", "job": job_snapshot(job)})


def log(job: Job, msg: str) -> None:
    line = {"t": round(time.time(), 3), "msg": str(msg)}
    job.logs.append(line)
    if len(job.logs) > 2000:
        del job.logs[:-2000]
    bus.emit({"type": "log", "job_id": job.id, "line": line})


def submit(kind: str, title: str, fn: Callable[[Job, Callable[[str], None]], Any],
           project_id: str = "") -> Job:
    job = Job(
        id=uuid.uuid4().hex[:10],
        kind=kind,
        title=title,
        project_id=project_id,
        created_at=time.time(),
    )
    JOBS[job.id] = job
    # 只保留最近 100 个任务
    if len(JOBS) > 100:
        for old_id in list(JOBS)[:-100]:
            JOBS.pop(old_id, None)
    _Q.put((job, fn))
    emit_job(job)
    return job


def has_running(project_id: str) -> bool:
    return any(
        j.project_id == project_id and j.status in ("queued", "running")
        for j in JOBS.values()
    )


def _worker() -> None:
    while True:
        job, fn = _Q.get()
        job.status = "running"
        job.started_at = time.time()
        emit_job(job)
        try:
            result = fn(job, lambda msg: log(job, msg))
            if result is not None:
                job.result = result  # type: ignore[attr-defined]
            job.status = "done"
            job.progress = 1.0
        except Exception as exc:  # noqa: BLE001 - 统一记录展示
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
            log(job, f"❌ 任务失败：{job.error}")
        finally:
            job.finished_at = time.time()
            emit_job(job)
            _Q.task_done()


threading.Thread(target=_worker, name="drama-job-worker", daemon=True).start()
