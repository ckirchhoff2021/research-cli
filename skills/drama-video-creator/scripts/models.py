"""领域数据模型：项目 / 剧本 / 分镜 / 角色。"""
from __future__ import annotations
import json, time, uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUS_CREATED = "created"
STATUS_SCRIPTED = "scripted"
STATUS_VOICED = "voiced"
STATUS_GENERATING = "generating"
STATUS_ASSEMBLED = "assembled"
STATUS_FAILED = "failed"

SHOT_PENDING = "pending"
SHOT_RUNNING = "running"
SHOT_DONE = "done"
SHOT_FAILED = "failed"

@dataclass
class Character:
    name: str = ""
    role: str = ""
    appearance: str = ""
    tag: str = ""
    voice_type: str = ""
    ref_image: str = ""

@dataclass
class Dialogue:
    character: str = ""
    text: str = ""
    voice_file: str = ""
    duration: float = 0.0
    start_offset: float = 2.0  # seconds after shot begins

@dataclass
class Shot:
    index: int = 0
    title: str = ""
    duration: int = 10
    scene: str = ""
    characters: list[str] = field(default_factory=list)
    action: str = ""
    emotion: str = ""
    dialogues: list[dict] = field(default_factory=list)
    prompt: str = ""
    video_file: str = ""
    status: str = SHOT_PENDING
    task_id: str = ""
    error: str = ""

@dataclass
class Script:
    title: str = ""
    genre: str = ""
    logline: str = ""
    theme: str = ""
    style_anchor: str = ""
    bgm_style: str = "gufeng"
    characters: list[dict] = field(default_factory=list)
    shots: list[dict] = field(default_factory=list)
    full_text: str = ""

@dataclass
class Project:
    id: str = ""
    name: str = ""
    concept: str = ""
    ratio: str = "16:9"
    resolution: str = "1080p"
    num_shots: int = 7
    style: str = "gufeng"
    script: dict = field(default_factory=dict)
    shots: list[dict] = field(default_factory=list)
    final_video: str = ""
    status: str = STATUS_CREATED
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self):
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data):
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

def new_project_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
