"""全局配置：路径、环境变量、默认参数。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（research-cli 仓库根）
REPO_ROOT = Path(__file__).resolve().parent.parent
CODING_DIR = Path(__file__).resolve().parent

load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class ModelConfig:
    """一组 OpenAI 协议兼容的模型配置。"""

    api_key: str
    base_url: str
    model: str

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


@dataclass(frozen=True)
class Settings:
    """框架运行配置。"""

    # ---- 路径 ----
    repo_root: Path = REPO_ROOT
    data_dir: Path = CODING_DIR / "data"
    sessions_db: Path = CODING_DIR / "data" / "sessions.db"
    checkpoints_db: Path = CODING_DIR / "data" / "checkpoints.db"
    static_dir: Path = CODING_DIR / "static"
    outputs_dir: Path = REPO_ROOT / "outputs"
    # 技能来源：仓库已有技能 + curator 自进化产出的技能
    skills_dirs: tuple[str, ...] = field(default_factory=lambda: ())
    memory_file: Path = CODING_DIR / "data" / "memory" / "AGENTS.md"

    # ---- 服务 ----
    host: str = "127.0.0.1"
    port: int = 8321

    # ---- curator ----
    curator_interval: float = 120.0
    curator_max_turns: int = 25

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            self.memory_file.write_text(
                "# Agent 长期记忆\n\n"
                "<!-- 本文件由 curator 自进化进程维护，也可手工编辑。 -->\n",
                encoding="utf-8",
            )


def brain_model() -> ModelConfig:
    """主模型（对话/任务执行）。"""
    return ModelConfig(
        api_key=os.getenv("BRAIN_API_KEY", ""),
        base_url=os.getenv("BRAIN_API_URL", ""),
        model=os.getenv("BRAIN_MODEL_NAME", ""),
    )


def optimizer_model() -> ModelConfig:
    """curator 自进化用的反思模型，缺省回退到主模型。"""
    cfg = ModelConfig(
        api_key=os.getenv("OPTIMIZER_API_KEY", ""),
        base_url=os.getenv("OPTIMIZER_API_URL", ""),
        model=os.getenv("OPTIMIZER_MODEL_NAME", ""),
    )
    return cfg if cfg.available else brain_model()


def get_settings() -> Settings:
    skills = []
    repo_skills = REPO_ROOT / "skills"
    curator_skills = CODING_DIR / "data" / "skills"
    if repo_skills.is_dir():
        skills.append(str(repo_skills))
    skills.append(str(curator_skills))
    settings = Settings(skills_dirs=tuple(skills))
    settings.ensure_dirs()
    curator_skills.mkdir(parents=True, exist_ok=True)
    return settings
