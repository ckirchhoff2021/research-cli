"""配置加载：.env回退链 + 路径 + ffmpeg探测。"""
from __future__ import annotations
import os, shutil
from pathlib import Path
from dotenv import load_dotenv

SKILL_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SKILL_DIR.parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "drama_video"

def load_env():
    loaded = []
    for candidate in [
        PROJECT_ROOT / ".env",
        Path.home() / ".config" / "research-cli" / ".env",
    ]:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            loaded.append(str(candidate))
    return loaded

def get_settings():
    load_env()
    return {
        "ark_api_key": os.getenv("ARK_API_KEY", "") or os.getenv("VOLCENGINE_API_KEY", ""),
        "ark_base_url": os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        "llm_model": os.getenv("BRAIN_MODEL_NAME", "doubao-1.5-pro-32k"),
        "video_model": os.getenv("VIDEO_GEN_MODEL", "doubao-seedance-2-0"),
        "image_model": os.getenv("IMAGE_GEN_MODEL", "doubao-seedream-4-5"),
        "tts_app_id": os.getenv("TTS_APP_ID", ""),
        "tts_access_token": os.getenv("TTS_ACCESS_TOKEN", ""),
    }

def find_ffmpeg():
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        if ff and Path(ff).exists():
            return ff
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    return found or ""

def project_dir(project_id):
    d = OUTPUTS_DIR / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def ensure_dirs(project_id):
    base = project_dir(project_id)
    for sub in ["characters", "voices", "segments"]:
        (base / sub).mkdir(exist_ok=True)
    return base
