"""Podcast Studio 业务层：语音合成（在线 TTS API）+ ffmpeg 拼接。

长文本自动按句切分多次合成，单次 API 失败不会毁掉整段节目。
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
STUDIO_DIR = HERE.parent
PROJECT_ROOT = STUDIO_DIR.parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# ── 工作区（按 AGENTS.md 规范归入 outputs 新类别目录） ──
WORKSPACE = PROJECT_ROOT / "outputs" / "20_播客工作室"
CLIPS_DIR = WORKSPACE / "clips"
EPISODES_DIR = WORKSPACE / "episodes"
TMP_DIR = WORKSPACE / ".tmp"
for _d in (CLIPS_DIR, EPISODES_DIR, TMP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

VOICE_LIST = PROJECT_ROOT / "skills" / "speech-generator" / "assets" / "voice_list.json"

# ── TTS API 配置 ─────────────────────────────────────
appid = os.getenv("TTS_APPID")
access_token = os.getenv("TTS_ACCESS_TOKEN")
cluster = os.getenv("TTS_CLUSTER")
tts_host = os.getenv("TTS_HOST", "")
API_URL = f"https://{tts_host}/api/v1/tts"
API_HEADER = {"Authorization": f"Bearer;{access_token}"}


def tts_configured() -> bool:
    return bool(appid and access_token and cluster and tts_host
                and "example.com" not in tts_host)


def _clamp(v, lo: float, hi: float, default: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


def load_voices() -> list[dict]:
    return json.loads(VOICE_LIST.read_text(encoding="utf-8"))


# ── ffmpeg ───────────────────────────────────────────
def find_ffmpeg() -> str:
    """多路径兜底：FFMPEG_PATH → hermes 工具仓 → PATH → imageio_ffmpeg。"""
    env = os.getenv("FFMPEG_PATH")
    if env and Path(env).exists():
        return env
    tools = Path(os.getenv("HERMES_RUNTIME_DIR",
                          str(Path.home() / ".hermes" / "tools")))
    if tools.exists():
        for cand in sorted(tools.glob("ffmpeg-*/ffmpeg"), reverse=True):
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        if ff and Path(ff).exists():
            return ff
    except Exception:
        pass
    raise RuntimeError("未找到 ffmpeg，请设置 FFMPEG_PATH 环境变量")


FFMPEG = find_ffmpeg()


def get_duration(path: Path) -> float:
    """解析 ffmpeg -i 输出中的时长（秒）；失败返回 0。"""
    try:
        p = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True,
                           text=True, timeout=20)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", p.stderr)
        if m:
            h, mm, ss = m.groups()
            return int(h) * 3600 + int(mm) * 60 + float(ss)
    except Exception:
        pass
    return 0.0


# ── 文本切分 ─────────────────────────────────────────
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;…\n])")


def split_text(text: str, max_len: int = 350) -> list[str]:
    """按句界切成长度 ≤ max_len 的小块；单句超长时再硬切。"""
    text = text.strip()
    if len(text) <= max_len:
        return [text] if text else []
    chunks, cur = [], ""
    for sent in _SENT_SPLIT.split(text):
        if not sent:
            continue
        if len(sent) > max_len:
            if cur:
                chunks.append(cur)
                cur = ""
            for i in range(0, len(sent), max_len):
                part = sent[i:i + max_len]
                if len(part) == max_len and i + max_len < len(sent):
                    chunks.append(part)
                else:
                    cur = part
        elif len(cur) + len(sent) <= max_len:
            cur += sent
        else:
            if cur:
                chunks.append(cur)
            cur = sent
    if cur:
        chunks.append(cur)
    return chunks


# ── TTS 单次请求 ─────────────────────────────────────
def _tts_request(text: str, voice_type: str, out_path: Path,
                 speed_ratio: float, volume_ratio: float,
                 pitch_ratio: float) -> None:
    request_json = {
        "app": {"appid": appid, "token": "access_token", "cluster": cluster},
        "user": {"uid": os.getenv("TTS_UID", "podcast_studio")},
        "audio": {
            "voice_type": voice_type,
            "encoding": "mp3",
            "speed_ratio": float(speed_ratio),
            "volume_ratio": float(volume_ratio),
            "pitch_ratio": float(pitch_ratio),
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "text_type": "plain",
            "operation": "query",
            "with_frontend": 1,
            "frontend_type": "unitTson",
        },
    }
    resp = requests.post(API_URL, json=request_json, headers=API_HEADER,
                         timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(
            f"TTS API HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"TTS 返回非 JSON：{resp.text[:200]}")
    if "data" not in data:
        msg = data.get("error", {}).get("message", "未知错误")
        raise RuntimeError(f"TTS 合成失败：{msg}")
    raw = base64.b64decode(data["data"])
    if len(raw) < 200:
        raise RuntimeError("TTS 返回数据异常（过小），文本可能含非法字符")
    out_path.write_bytes(raw)


def synthesize(text: str, voice_type: str, out_path: Path, *,
               speed_ratio: float = 1.0, volume_ratio: float = 1.0,
               pitch_ratio: float = 1.0, log=None) -> Path:
    """合成一段文本；长文本自动切块后用 ffmpeg 无缝拼接。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("合成文本不能为空")
    if not voice_type:
        raise ValueError("未选择音色")
    chunks = split_text(text)
    if len(chunks) == 1:
        _tts_request(chunks[0], voice_type, out_path,
                     speed_ratio, volume_ratio, pitch_ratio)
        return out_path

    jobdir = TMP_DIR / f"seg_{uuid.uuid4().hex[:8]}"
    jobdir.mkdir(parents=True, exist_ok=True)
    parts = []
    try:
        for i, chunk in enumerate(chunks):
            part = jobdir / f"part_{i:03d}.mp3"
            _tts_request(chunk, voice_type, part,
                         speed_ratio, volume_ratio, pitch_ratio)
            parts.append(part)
            if log:
                log(f"   语音块 {i + 1}/{len(chunks)} 完成")
        _concat_mp3(parts, out_path)
    finally:
        shutil.rmtree(jobdir, ignore_errors=True)
    return out_path


def _run_ffmpeg(args: list[str]) -> None:
    p = subprocess.run([FFMPEG, "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败：{p.stderr[-400:]}")


def _concat_mp3(parts: list[Path], out_path: Path) -> None:
    """filter_complex concat：各自解码，容忍采样率/编码参数差异。"""
    if len(parts) == 1:
        shutil.copy2(parts[0], out_path)
        return
    inputs, labels = [], []
    for i, part in enumerate(parts):
        inputs += ["-i", str(part)]
        labels.append(f"[{i}:a]")
    chain = "".join(labels) + f"concat=n={len(parts)}:v=0:a=1[out]"
    _run_ffmpeg([*inputs, "-filter_complex", chain, "-map", "[out]",
                 "-c:a", "libmp3lame", "-q:a", "2", str(out_path)])


# ── 完整节目 ─────────────────────────────────────────
def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _slug(title: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", (title or "").strip())[:40]
    return s.strip("_") or "untitled"


def build_episode(title: str, segments: list[dict], log,
                  set_progress) -> dict:
    """逐段合成 → 拼接为一整期 MP3。"""
    clean = []
    for i, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        voice = (seg.get("voice") or "").strip()
        if not text:
            raise ValueError(f"第 {i + 1} 段台词为空")
        if not voice:
            raise ValueError(f"第 {i + 1} 段未选择音色")
        clean.append({
            "text": text,
            "voice": voice,
            "speed": _clamp(seg.get("speed"), 0.8, 1.5, 1.0),
            "volume": _clamp(seg.get("volume"), 0.8, 1.5, 1.0),
            "pitch": _clamp(seg.get("pitch"), 0.8, 1.2, 1.0),
        })
    if not clean:
        raise ValueError("节目至少需要一段台词")

    jobdir = TMP_DIR / f"ep_{uuid.uuid4().hex[:8]}"
    jobdir.mkdir(parents=True, exist_ok=True)
    clip_names = []
    stamp = _stamp()
    try:
        seg_files = []
        for i, seg in enumerate(clean):
            log(f"🎙 第 {i + 1}/{len(clean)} 段合成中：{seg['text'][:30]}…")
            f = jobdir / f"seg_{i:03d}.mp3"
            synthesize(seg["text"], seg["voice"], f,
                       speed_ratio=seg["speed"], volume_ratio=seg["volume"],
                       pitch_ratio=seg["pitch"], log=log)
            seg_files.append(f)
            set_progress((i + 1) / (len(clean) + 1))

        name = f"{stamp}_{_slug(title)}.mp3"
        out = EPISODES_DIR / name
        log("🔪 ffmpeg 拼接整期节目…")
        _concat_mp3(seg_files, out)

        # 每段成品同时留存 clips，方便单段复用
        for i, f in enumerate(seg_files):
            cn = f"{stamp}_{_slug(title)}_s{i + 1}.mp3"
            shutil.copy2(f, CLIPS_DIR / cn)
            clip_names.append(cn)
    finally:
        shutil.rmtree(jobdir, ignore_errors=True)

    set_progress(1.0)
    return {
        "name": out.name,
        "url": f"/media/episodes/{out.name}",
        "duration": get_duration(out),
        "clips": clip_names,
    }


def save_clip(text: str, voice: str, *, speed_ratio: float = 1.0,
              volume_ratio: float = 1.0, pitch_ratio: float = 1.0,
              log=None) -> dict:
    name = f"{_stamp()}_clip.mp3"
    out = CLIPS_DIR / name
    synthesize(text, voice, out, speed_ratio=speed_ratio,
               volume_ratio=volume_ratio, pitch_ratio=pitch_ratio, log=log)
    return {"name": name, "url": f"/media/clips/{name}",
            "duration": get_duration(out)}


# ── 音频库 ───────────────────────────────────────────
def _scan(d: Path, kind: str) -> list[dict]:
    if not d.exists():
        return []
    items = []
    for f in d.iterdir():
        if f.suffix.lower() != ".mp3" or f.name.startswith("."):
            continue
        st = f.stat()
        items.append({
            "kind": kind,
            "name": f.name,
            "url": f"/media/{kind}/{f.name}",
            "size": st.st_size,
            "mtime": st.st_mtime,
            "duration": get_duration(f),
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def library() -> dict:
    return {"clips": _scan(CLIPS_DIR, "clips"),
            "episodes": _scan(EPISODES_DIR, "episodes")}


def delete_media(kind: str, name: str) -> None:
    if kind not in ("clips", "episodes"):
        raise ValueError("非法类别")
    p = Path(name)
    if p.name != name or not name.endswith(".mp3"):
        raise ValueError("非法文件名")
    target = (CLIPS_DIR if kind == "clips" else EPISODES_DIR) / name
    if not target.exists():
        raise FileNotFoundError("文件不存在")
    target.unlink()
