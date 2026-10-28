"""短剧 pipeline 的细粒度封装：每个环节都可单独触发、重试与人工编辑。

底层复用 skills/drama-video-creator 的既有模块：
creative（LLM剧本/分镜prompt）、image/video generator、TTS、compose。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
HERE = Path(__file__).resolve().parent                      # backend
STUDIO_DIR = HERE.parent                                   # drama_studio
PROJECT_ROOT = STUDIO_DIR.parent.parent                    # research-cli
SKILL_SCRIPTS = PROJECT_ROOT / "skills" / "drama-video-creator" / "scripts"
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "drama_video"

IMAGE_GEN_SCRIPT = PROJECT_ROOT / "skills" / "image-generator" / "scripts" / "generator.py"
VIDEO_GEN_SCRIPT = PROJECT_ROOT / "skills" / "video-generator" / "scripts" / "generator.py"
TTS_SCRIPT = PROJECT_ROOT / "skills" / "speech-generator" / "scripts" / "tts.py"
IMG_OUT_DIR = PROJECT_ROOT / "skills" / "image-generator" / "outputs"
VID_OUT_DIR = PROJECT_ROOT / "skills" / "video-generator" / "outputs"
VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python"

sys.path.insert(0, str(SKILL_SCRIPTS))
from config import ensure_dirs, find_ffmpeg, get_settings  # noqa: E402
from creative import (  # noqa: E402
    build_shot_prompts, generate_script, refine_script,
    pick_voice, infer_gender,
    DEFAULT_MALE_VOICE, DEFAULT_FEMALE_VOICE,
)
from creative import generate_shot as llm_generate_shot  # noqa: E402
from compose import compose_final  # noqa: E402

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ── 项目 IO ───────────────────────────────────────────
def list_projects() -> list[dict]:
    out = []
    if not OUTPUTS_DIR.exists():
        return out
    for d in OUTPUTS_DIR.iterdir():
        pf = d / "project.json"
        if d.is_dir() and pf.exists():
            out.append(json_load(pf))
    out.sort(key=lambda p: p.get("updated_at", 0), reverse=True)
    return out


def json_load(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def load(project_id: str) -> dict:
    pf = OUTPUTS_DIR / project_id / "project.json"
    if not pf.exists():
        raise FileNotFoundError(f"项目不存在: {project_id}")
    data = json_load(pf)
    # 磁盘反序列化后 script.shots 与顶层 shots 是两份数据，
    # 统一为同一引用，保证 rebuild_prompts 的修改能反映到顶层。
    if data.get("shots") is not None:
        data.setdefault("script", {})["shots"] = data["shots"]
    # 迁移：为缺少 uid 的镜头补稳定 ID。
    # 素材文件（segments/voices）按 uid 命名，拖拽排序改变位置后不会错绑或互相覆盖。
    migrated = False
    for shot in data.get("shots", []):
        if not shot.get("uid"):
            shot["uid"] = "shot_" + uuid.uuid4().hex[:10]
            migrated = True
    if migrated:
        try:
            save(data)
        except OSError:
            pass
    return data


def save(project: dict) -> None:
    import json
    project["updated_at"] = time.time()
    # 保持 script.shots 与 project.shots 同步
    project.setdefault("script", {})["shots"] = project.get("shots", [])
    pf = OUTPUTS_DIR / project["id"] / "project.json"
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")


def new_pid(name: str = "") -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    suffix = re.sub(r"[^\w]", "_", name)[:10] if name else ""
    return f"{ts}-{suffix}" if suffix else ts


def rebuild_prompts(project: dict) -> None:
    """根据当前剧本/角色/分镜内容重建每个镜头的视频生成 prompt。"""
    build_shot_prompts(project["script"])


def generate_shot(project: dict, user_prompt: str) -> dict:
    """根据用户提示词，结合已有风格/角色/分镜，用 LLM 生成一个镜头的内容（不落盘）。"""
    settings = get_settings()
    script = project.get("script", {})
    context = {
        "style_anchor": script.get("style_anchor", ""),
        "characters": script.get("characters", []),
        "shots": project.get("shots", []),
    }
    return llm_generate_shot(user_prompt.strip(), context, settings)


def reorder_shots(project: dict, order: list[int]) -> None:
    """按给定的旧序号（1-based）重排镜头，并重写 index / prompt。"""
    shots = project.get("shots", [])
    n = len(shots)
    if (
        not isinstance(order, list)
        or len(order) != n
        or sorted(order) != list(range(1, n + 1))
    ):
        raise ValueError("排序参数无效：必须包含全部镜头且无重复")
    project["shots"] = [shots[i - 1] for i in order]
    for i, shot in enumerate(project["shots"]):
        shot["index"] = i + 1
    # 保持 script.shots 与顶级 shots 为同一列表
    project["script"]["shots"] = project["shots"]
    project["num_shots"] = n
    rebuild_prompts(project)


def parse_tts_feedback(feedback: str) -> tuple[float, float, float]:
    """把自然语言反馈映射为 TTS 的 (语速, 音量, 音调)。范围做安全截断。"""
    speed = vol = pitch = 1.0
    f = feedback or ""
    if any(k in f for k in ("慢", "放缓", "放慢")):
        speed = 0.85
    if any(k in f for k in ("快", "加快")):
        speed = 1.15
    if any(k in f for k in ("大声", "洪亮", "响亮", "再响", "音量大", "大点", "大一点")):
        vol = 1.2
    if any(k in f for k in ("小声", "轻声", "温柔", "压低声音", "音量小", "轻点", "小一点")):
        vol = 0.85
    if any(k in f for k in ("低沉", "低音", "稳重", "浑厚")):
        pitch = 0.9
    if any(k in f for k in ("高亢", "高音", "明亮", "上扬")):
        pitch = 1.1
    speed = min(1.5, max(0.7, speed))
    vol = min(1.5, max(0.7, vol))
    pitch = min(1.3, max(0.7, pitch))
    return speed, vol, pitch


def parse_voice_override(feedback: str) -> str:
    """从反馈里识别“换音色”诉求，返回 voice_type；未识别返回 ''。"""
    f = feedback or ""
    wants_male = any(k in f for k in (
        "男声", "男生", "男的", "换成男", "用男", "男音"))
    female_style = any(k in f for k in (
        "御姐", "少女", "萝莉", "奶奶", "婆婆", "老妇", "老太太",
        "女声", "女生", "女的", "换成女", "用女", "女音", "女性",
        "温婉", "温柔女", "甜美", "妩媚"))
    # 显式要求男声优先（避免“温柔男声”误入女声）
    if wants_male and not any(k in f for k in ("女声", "女生")):
        if any(k in f for k in ("老", "沧桑")):
            return "zh_male_bv139_audiobook_ummv3_bigtts"
        if any(k in f for k in ("冷峻", "冷漠", "沉稳", "深沉")):
            return "ICL_zh_male_lengjungaozhi_tob"
        if any(k in f for k in ("旁白", "解说", "磁性")):
            return "zh_male_jieshuonansheng_mars_bigtts"
        if any(k in f for k in ("少年", "清朗", "年轻", "阳光")):
            return "ICL_zh_male_shuanglangshaonian_tob"
        return DEFAULT_MALE_VOICE
    if female_style:
        if any(k in f for k in ("奶奶", "婆婆", "老妇", "老太太")):
            return "ICL_zh_female_heainainai_tob"
        if any(k in f for k in ("御姐", "高冷", "清冷", "成熟", "妩媚", "女王")):
            return "zh_female_gaolengyujie_moon_bigtts"
        if any(k in f for k in ("甜美", "少女", "可爱", "萝莉", "清纯")):
            return "zh_female_tianmeixiaoyuan_moon_bigtts"
        if any(k in f for k in ("活泼", "俏皮", "开朗", "元气")):
            return "ICL_zh_female_huoponvhai_tob"
        if any(k in f for k in ("温柔", "温婉")):
            return DEFAULT_FEMALE_VOICE
        return DEFAULT_FEMALE_VOICE
    return ""


# ── 子进程执行（心跳 + 超时 + 输出捕获） ───────────────
def run_proc(cmd: list[str], log, timeout: int = 1800, heartbeat: int = 15) -> int:
    import queue as _q
    import threading

    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(PROJECT_ROOT),
        bufsize=1,
    )
    q: _q.Queue[str | None] = _q.Queue()

    def _reader() -> None:
        assert p.stdout is not None
        for line in p.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    t0 = time.time()
    last_beat = t0
    captured: list[str] = []
    while True:
        try:
            item = q.get(timeout=0.8)
        except _q.Empty:
            item = False  # type: ignore[assignment]
        if item is None:
            break
        if item:
            clean = item.rstrip().replace("\r", "")
            if clean:
                captured.append(clean)
        now = time.time()
        if now - last_beat > heartbeat:
            log(f"⏳ 生成中… 已耗时 {now - t0:.0f}s")
            last_beat = now
        if now - t0 > timeout:
            p.kill()
            raise TimeoutError(f"子进程超过 {timeout}s 超时")
    rc = p.wait()
    for line in captured[-12:]:
        log("  " + line[:300])
    return rc, captured


# ── 环节1：创意 → 剧本 + 分镜 + 角色定妆照 ─────────────
def create_project(payload: dict, log) -> str:
    settings = get_settings()
    concept = payload["concept"].strip()
    num_shots = int(payload.get("shots", 7))
    ratio = payload.get("ratio", "16:9")
    resolution = payload.get("resolution", "1080p")
    style = payload.get("style", "gufeng")

    pid = new_pid(concept[:8])
    ensure_dirs(pid)
    log(f"🎬 新建项目 {pid}")
    log(f"   创意：{concept}")
    log(f"   分镜 {num_shots} 个｜{ratio}｜{resolution}｜风格 {style}")

    log("✍️  LLM 创作剧本与分镜…")
    script_data = generate_script(concept, num_shots, style, ratio, resolution, settings)
    log(f"   片名：{script_data.get('title', '')}")
    log(f"   角色：{'、'.join(c['name'] for c in script_data.get('characters', []))}")

    shots = build_shot_prompts(script_data)
    for s in shots:
        s["status"] = "pending"
        s["video_file"] = ""
        s["voices"] = []
    script_data["shots"] = shots

    project = {
        "id": pid,
        "name": script_data.get("title", concept[:20]),
        "concept": concept,
        "ratio": ratio,
        "resolution": resolution,
        "num_shots": num_shots,
        "style": style,
        "script": script_data,
        "shots": shots,
        "final_video": "",
        "status": "scripted",
        "error": "",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    save(project)

    log("🖼  生成角色定妆参考图…")
    for c in script_data.get("characters", []):
        gen_character_image(project, c["name"], log)
    save(project)
    log("✅ 剧本环节完成，可在「剧本 / 角色 / 分镜」页人工调整后再继续。")
    return pid


def regenerate_script(project: dict, log, feedback: str = "") -> None:
    """保留项目 id/媒体设置，用 LLM 重新生成剧本、分镜并重建角色定妆照。"""
    settings = get_settings()
    feedback = (feedback or "").strip()
    if feedback:
        log(f"✍️  根据反馈调整剧本：{feedback}")
        script_data = refine_script(
            project["concept"], project.get("script", {}), feedback,
            project["ratio"], project["resolution"], settings,
        )
    else:
        log("✍️  AI 重新生成剧本…")
        script_data = generate_script(
            project["concept"], project["num_shots"], project["style"],
            project["ratio"], project["resolution"], settings,
        )
    shots = build_shot_prompts(script_data)
    for s in shots:
        s["status"] = "pending"
        s["video_file"] = ""
        s["voices"] = []
    script_data["shots"] = shots
    project["script"] = script_data
    project["shots"] = shots
    project["name"] = script_data.get("title", project["name"])
    project["status"] = "scripted"
    project["final_video"] = ""
    save(project)
    log("🖼  重新生成角色定妆参考图…")
    for c in script_data.get("characters", []):
        gen_character_image(project, c["name"], log)
    save(project)


# ── 环节2：角色定妆照 ─────────────────────────────────
def gen_character_image(project: dict, char_name: str, log, feedback: str = "") -> None:
    chars = project.get("script", {}).get("characters", [])
    char = next((c for c in chars if c["name"] == char_name), None)
    if char is None:
        raise ValueError(f"角色不存在: {char_name}")
    base = ensure_dirs(project["id"])
    chars_dir = base / "characters"
    ref_path = chars_dir / f"ref_{char_name}.jpg"
    style_hint = project.get("script", {}).get("style_anchor", "国风3D CG动画风格")
    feedback = (feedback or "").strip()
    # 强制“单人肖像”：避免模型脑补路人/配角，或把“角色设定图”理解成多人设定板
    prompt = (
        f"{style_hint}。单人角色定妆肖像照，画面中有且仅有{char_name}这一个人物，"
        f"人物外观：{char.get('appearance', '')}，气质标签：{char.get('tag', '')}。"
        "构图要求：人物位于画面正中，胸部以上的单人胸像，面部清晰，正对镜头，"
        "背景简洁、柔和虚化，不要任何其他人物，不要路人，不要多人合影，不要人群，"
        "不要多视图，不要角色对照板，不要文字、标签、水印。"
        "画面必须是3D CG动画/卡通渲染质感（类似皮克斯、迪士尼动画电影角色），"
        "皮肤与光影为动画渲染效果，严禁真人照片质感，严禁真实摄影人像，严禁写实胶片感。"
    )
    if feedback:
        prompt += f"本次调整要求：{feedback}（仍须保持画面中只有{char_name}一人）。"
    log(f"🖼  生成「{char_name}」定妆照…")
    if feedback: log(f"   反馈：{feedback}")
    rc, _ = run_proc(
        [str(VENV_PY), str(IMAGE_GEN_SCRIPT), "--prompt", prompt, "--size", "2K"],
        log, timeout=300, heartbeat=20,
    )
    imgs = sorted(IMG_OUT_DIR.glob("dream_*.jpg"), key=os.path.getmtime) if IMG_OUT_DIR.exists() else []
    if not imgs:
        raise RuntimeError(f"定妆照生成失败（rc={rc}），未取得图像产物")
    shutil.copy(imgs[-1], ref_path)
    char["ref_image"] = str(ref_path)
    save(project)
    log(f"   ✓ {ref_path.name}")


# ── 环节3：对白配音 ───────────────────────────────────
def _audio_duration(path: Path, text: str) -> float:
    try:
        from moviepy import AudioFileClip
        c = AudioFileClip(str(path))
        d = float(c.duration)
        c.close()
        return round(d, 2)
    except Exception:
        return round(len(text) * 0.25, 2)


def gen_shot_voices(project: dict, shot_index: int, log,
                    feedback: str = "", voice_override: str = "") -> None:
    """shot_index 为 0-based。"""
    base = ensure_dirs(project["id"])
    voices_dir = base / "voices"
    chars = {c["name"]: c for c in project.get("script", {}).get("characters", [])}
    shot = project["shots"][shot_index]
    uid = shot.get("uid") or ("shot_" + uuid.uuid4().hex[:10])
    shot["uid"] = uid
    entries = []
    feedback = (feedback or "").strip()
    voice_override = (voice_override or "").strip()
    speed, vol, pitch = parse_tts_feedback(feedback)
    feedback_voice = parse_voice_override(feedback)
    named_chars = {cn for cn in chars if cn and cn in feedback}
    if feedback:
        log(f"🎧 配音反馈：{feedback}")
        extra = f"｜音色→{feedback_voice}" if feedback_voice else ""
        scope_note = f"（仅对：{'、'.join(sorted(named_chars))}）" if feedback_voice and named_chars else ""
        log(f"   → 语速 {speed}｜音量 {vol}｜音调 {pitch}{extra}（未识别的词不影响生成）{scope_note}")
    for di, d in enumerate(shot.get("dialogues", [])):
        text = (d.get("text") or "").strip()
        if not text:
            continue
        char_name = d.get("character", "")
        char = chars.get(char_name, {})
        role_feedback_voice = ""
        if feedback_voice and (not named_chars or char_name in named_chars):
            role_feedback_voice = feedback_voice
        voice_type = (
            voice_override
            or role_feedback_voice
            or char.get("voice_type")
            or pick_voice(char.get("voice_hint", ""), infer_gender(char))
        )
        fname = f"{uid}_d{di+1}_{char_name}.mp3"
        out = voices_dir / fname
        if (role_feedback_voice or voice_override) and out.exists():
            out.unlink()  # 带反馈重生成：清掉旧音频
        if not out.exists() or os.path.getsize(out) < 100:
            log(f"🎙  镜头{shot_index+1:02d} {char_name}（{voice_type}）：{text[:24]}")
            rc, _ = run_proc(
                [str(VENV_PY), str(TTS_SCRIPT),
                 "--tts_text", text,
                 "--voice_type", voice_type,
                 "--output_file", str(out),
                 "--speed_ratio", str(speed),
                 "--volume_ratio", str(vol),
                 "--pitch_ratio", str(pitch)],
                log, timeout=180, heartbeat=30,
            )
            if not out.exists():
                raise RuntimeError(f"配音生成失败（rc={rc}）: {char_name}")
        entries.append({
            "character": char_name,
            "text": text,
            "voice_file": str(out),
            "voice_type": voice_type,
            "duration": _audio_duration(out, text),
            "start_offset": d.get("start_offset", 2.5),
        })
    shot["voices"] = entries
    project["status"] = "voiced"
    save(project)
    log(f"✅ 镜头{shot_index+1:02d} 配音完成（{len(entries)} 条）")


def gen_all_voices(project: dict, log,
                   feedback: str = "", voice_override: str = "") -> None:
    for si in range(len(project["shots"])):
        gen_shot_voices(project, si, log,
                        feedback=feedback, voice_override=voice_override)


# ── 环节4：视频片段 ───────────────────────────────────
def gen_shot_video(project: dict, shot_index: int, log,
                   force: bool = False, feedback: str = "") -> None:
    base = ensure_dirs(project["id"])
    segs_dir = base / "segments"
    shot = project["shots"][shot_index]
    uid = shot.get("uid") or ("shot_" + uuid.uuid4().hex[:10])
    shot["uid"] = uid
    dest = segs_dir / f"{uid}.mp4"
    feedback = (feedback or "").strip()
    if feedback:
        force = True
    # 以镜头自己记录的 video_file 为准（可能是旧版的 shot_XX.mp4），
    # 不能按当前位置的文件判断，否则排序后会把别的镜头的视频误当成自己的。
    existing = Path(shot["video_file"]) if shot.get("video_file") else None
    if (
        not force
        and existing is not None
        and existing.exists()
        and existing.stat().st_size > 500_000
    ):
        shot["status"] = "done"
        save(project)
        log(f"⏭  镜头{shot_index+1:02d} 视频已存在（{existing.name}），跳过")
        return
    if force and dest.exists():
        dest.unlink()

    chars = {c["name"]: c for c in project.get("script", {}).get("characters", [])}
    char_refs: list[tuple[str, str]] = []   # (角色名, 定妆照路径)
    for cn in shot.get("characters", []):
        ri = chars.get(cn, {}).get("ref_image", "")
        if ri and os.path.exists(ri):
            char_refs.append((cn, ri))
    chars_dir = base / "characters"

    prompt = shot.get("prompt", "")

    def build_cmd(p: str, image_paths: list[str]) -> list[str]:
        cmd = [str(VENV_PY), str(VIDEO_GEN_SCRIPT),
               "--prompt", p,
               "--ratio", project["ratio"],
               "--duration", str(shot.get("duration", 10)),
               "--resolution", project["resolution"]]
        if image_paths:
            cmd += ["--images", ",".join(image_paths)]
        return cmd

    log(f"🎥 生成镜头{shot_index+1:02d}：{shot.get('title', '')}")
    log(f"   角色：{'、'.join(shot.get('characters', [])) or '（无）'}")
    if feedback: log(f"   反馈：{feedback}")

    # 关键：记录运行前已存在的产物，只接受本次新生成的文件，
    # 避免 API 失败时误把历史旧视频当成新结果（假成功）。
    def _snapshot() -> set[str]:
        if not VID_OUT_DIR.exists():
            return set()
        return {str(p) for p in VID_OUT_DIR.glob("dance_*.mp4")}

    def _new_mp4(before: set[str]) -> str | None:
        if not VID_OUT_DIR.exists():
            return None
        fresh = [p for p in VID_OUT_DIR.glob("dance_*.mp4")
                 if str(p) not in before and os.path.getsize(p) > 100_000]
        if not fresh:
            return None
        return str(max(fresh, key=os.path.getmtime))

    # ── 降级阶梯：原图 → 自动卡通化图 → 纯文本 ──────────────
    CG_PREFIX = "3D CG动画电影风格，卡通渲染质感，非真人照片，虚构角色。"

    def cartoonize(src: str, cn: str) -> str | None:
        """把定妆照自动风格化为 3D 动画质感（五官/服装/姿势不变），产出 ref_<角色>_toon.jpg。"""
        toon = chars_dir / f"ref_{cn}_toon.jpg"
        if toon.exists() and os.path.getsize(toon) > 20_000:
            return str(toon)
        before_img = ({str(p) for p in IMG_OUT_DIR.glob("dream_*.jpg")}
                      if IMG_OUT_DIR.exists() else set())
        stylize = (
            "把这张人物图像转换成3D CG动画电影风格：保持人物五官特征、发型、服装款式与配色、"
            "配饰、姿势完全不变，仅把皮肤质感、光影和整体画面渲染为皮克斯/迪士尼式卡通动画效果，"
            "非真人照片，背景同步做同风格动画化。"
        )
        log(f"   🎨 自动卡通化定妆照：{cn}…")
        run_proc(
            [str(VENV_PY), str(IMAGE_GEN_SCRIPT),
             "--prompt", stylize, "--image", src, "--size", "2K"],
            log, timeout=300, heartbeat=20,
        )
        fresh = [p for p in (IMG_OUT_DIR.glob("dream_*.jpg") if IMG_OUT_DIR.exists() else [])
                 if str(p) not in before_img and os.path.getsize(p) > 20_000]
        if fresh:
            out_img = str(max(fresh, key=os.path.getmtime))
            shutil.copy(out_img, toon)
            return str(toon)
        log("      卡通化未取得产物，继续下一级降级")
        return None

    last_err = ""
    produced = None
    privacy_blocked = False
    level = 0 if char_refs else 2          # 0=原图 1=卡通化图 2=纯文本
    active_refs = [p for _, p in char_refs]
    word_retried = False
    for attempt in range(4):
        use_prompt = prompt
        if level == 2:
            use_prompt = CG_PREFIX + use_prompt
        if feedback:
            use_prompt = f"{use_prompt}。本次调整要求：{feedback}。"
        image_paths = active_refs if level < 2 else []
        cmd = build_cmd(use_prompt, image_paths)
        before = _snapshot()
        rc, out_lines = run_proc(cmd, log, timeout=1800, heartbeat=20)
        produced = _new_mp4(before)
        if rc == 0 and produced:
            break
        joined = "\n".join(out_lines)
        last_err = joined[-300:]
        privacy_blocked = any(k in joined for k in (
            "Sensitive", "Privacy", "PrivacyInformation", "隐私"))
        if privacy_blocked:
            if level == 0 and char_refs:
                log("   ⚠️ 定妆照被判定可能含真人，自动卡通化后重试（第1级降级）…")
                tooned = []
                for cn, src in char_refs:
                    t = cartoonize(src, cn)
                    if t:
                        tooned.append(t)
                if tooned:
                    active_refs = tooned
                    level = 1
                else:
                    level = 2
                continue
            if level == 1:
                log("   ⚠️ 卡通化定妆照仍触发审核，去掉参考图、纯文本生成（第2级降级）…")
                active_refs = []
                level = 2
                continue
        # 非隐私类错误：改写敏感词后同级别重试一次
        if not word_retried:
            word_retried = True
            log("   未取得产物，调整措辞后重试…")
            feedback = feedback.replace("打斗", "对峙").replace("杀死", "击败")
            prompt = prompt.replace("打斗", "对峙").replace("杀死", "击败")
            continue
        break

    if not produced:
        shot["status"] = "failed"
        if privacy_blocked:
            shot["error"] = "三级降级后仍触发人脸/隐私审核"
            save(project)
            raise RuntimeError(
                f"镜头{shot_index+1:02d} 生成失败：定妆照持续被判定可能含真人。"
                f"已依次尝试【原图 → 自动卡通化图 → 纯文本】三级降级仍未成功。"
                f"请到角色环节点「重生成定妆照」（系统已内置强卡通提示），"
                f"或把外观描述改得更动画化后再试。原始错误：{last_err[-200:]}")
        shot["error"] = f"generation failed: {last_err[:120]}"
        save(project)
        raise RuntimeError(f"镜头{shot_index+1:02d} 视频生成失败：{last_err[-200:]}")

    shutil.copy(produced, dest)
    shot["video_file"] = str(dest)
    shot["status"] = "done"
    shot["error"] = ""
    project["status"] = "generating"
    save(project)
    via = ("原始定妆照" if level == 0 else "卡通化定妆照" if level == 1 else "纯文本")
    log(f"✅ 镜头{shot_index+1:02d} 完成（{via}）→ {dest.name} ({os.path.getsize(dest)/1024/1024:.1f}MB)")


def glob_latest() -> str | None:
    if not VID_OUT_DIR.exists():
        return None
    mp4s = list(VID_OUT_DIR.glob("dance_*.mp4"))
    if not mp4s:
        return None
    return str(max(mp4s, key=os.path.getmtime))


def gen_all_videos(project: dict, log, force: bool = False, feedback: str = "") -> None:
    for si in range(len(project["shots"])):
        gen_shot_video(project, si, log, force=force, feedback=feedback)


# ── 环节5：合成成片 ───────────────────────────────────
def compose(project: dict, log) -> None:
    base = ensure_dirs(project["id"])
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("未找到 ffmpeg")
    log("🎞  开始合成成片（片头片尾/转场/对白对齐/BGM）…")
    compose_final(project, base, VENV_PY, ff, PROJECT_ROOT)
    project["status"] = "assembled"
    save(project)
    log(f"✅ 成片完成：{project.get('final_video', '')}")


def run_remaining(project: dict, log) -> None:
    """补齐缺失的配音/视频片段后合成成片。"""
    total = len(project["shots"])
    for si, shot in enumerate(project["shots"]):
        if not shot.get("voices"):
            gen_shot_voices(project, si, log)
    for si, shot in enumerate(project["shots"]):
        vf = shot.get("video_file", "")
        if not vf or not os.path.exists(vf):
            gen_shot_video(project, si, log)
        log(f"   进度 {si+1}/{total}")
    compose(project, log)
