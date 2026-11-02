"""Image Studio 业务层：文生图 / 图生图编辑 / 风格迁移，全部走 image-generator 子进程。

关键防呆：运行前快照输出目录，只接受本次新产生的图片，API 失败时绝不把旧图当新结果。
"""
from __future__ import annotations

import os
import queue as _q
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIO_DIR = HERE.parent
PROJECT_ROOT = STUDIO_DIR.parent.parent
IMAGE_GEN_SCRIPT = PROJECT_ROOT / "skills" / "image-generator" / "scripts" / "generator.py"
GEN_OUT_DIR = PROJECT_ROOT / "skills" / "image-generator" / "outputs"
VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python"

# 工作区（按 AGENTS.md 规范归入 outputs 新类别目录）
WORKSPACE = PROJECT_ROOT / "outputs" / "17_AI图像工作室"
UPLOADS_DIR = WORKSPACE / "uploads"
GENERATED_DIR = WORKSPACE / "generated"
EDITS_DIR = WORKSPACE / "edits"
for d in (UPLOADS_DIR, GENERATED_DIR, EDITS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DIR_MAP = {"uploads": UPLOADS_DIR, "generated": GENERATED_DIR, "edits": EDITS_DIR}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# ── 子进程执行（心跳 + 输出捕获） ─────────────────────
def run_proc(cmd: list[str], log, timeout: int = 600, heartbeat: int = 15):
    p = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, cwd=str(PROJECT_ROOT), bufsize=1,
    )
    q: _q.Queue[str | None] = _q.Queue()

    def _reader() -> None:
        assert p.stdout is not None
        for line in p.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    t0, last_beat, captured = time.time(), time.time(), []
    while True:
        try:
            item = q.get(timeout=0.8)
        except _q.Empty:
            item = False
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


def _snapshot() -> set[str]:
    if not GEN_OUT_DIR.exists():
        return set()
    return {str(x) for x in GEN_OUT_DIR.glob("dream_*")}


def run_generator(final_prompt: str, image_paths: list[str], size: str, log) -> Path:
    """调 generator.py 子进程，只接受本次新产出的图（防假成功）。返回新图 Path。"""
    cmd = [str(VENV_PY), str(IMAGE_GEN_SCRIPT), "--prompt", final_prompt, "--size", size]
    for ip in image_paths:
        if ip and os.path.exists(ip):
            cmd += ["--image", ip]
    before = _snapshot()
    rc, lines = run_proc(cmd, log, timeout=600, heartbeat=15)
    fresh = [Path(x) for x in (GEN_OUT_DIR.glob("dream_*") if GEN_OUT_DIR.exists() else [])
             if str(x) not in before and x.suffix.lower() in IMG_EXTS and os.path.getsize(x) > 20_000]
    if rc != 0 or not fresh:
        tail = "\n".join(lines[-8:])
        raise RuntimeError(f"图像生成失败（rc={rc}）：{tail[-400:]}")
    return Path(max(fresh, key=os.path.getmtime))


def generate_image(prompt: str, image_paths: list[str], size: str,
                   mode: str, feedback: str, log) -> str:
    """mode: text2image | edit | style。返回归档后的图片绝对路径。"""
    prompt = (prompt or "").strip()
    feedback = (feedback or "").strip()
    if not prompt:
        raise ValueError("提示词不能为空")

    # 反馈与模式引导
    final_prompt = prompt
    if mode == "style":
        final_prompt = f"保持原图人物五官、构图与主体不变，整体风格转换为：{prompt}"
    if feedback:
        final_prompt = f"{final_prompt}。本次调整要求：{feedback}"

    cmd = [str(VENV_PY), str(IMAGE_GEN_SCRIPT), "--prompt", final_prompt, "--size", size]
    for ip in image_paths:
        if ip and os.path.exists(ip):
            cmd += ["--image", ip]

    mode_label = {"text2image": "🎨 文生图", "edit": "🖌 图像编辑", "style": "🌊 风格迁移"}.get(mode, "🎨 图像生成")
    log(f"{mode_label}：{prompt[:60]}")
    if image_paths:
        log(f"   参考图 {len(image_paths)} 张：{', '.join(Path(x).name for x in image_paths)}")
    if feedback:
        log(f"   反馈：{feedback}")

    src = run_generator(final_prompt, image_paths, size, log)
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest = GENERATED_DIR / f"{mode}_{ts}.jpg"
    # 统一转码为标准 RGB JPEG（处理 PNG/带透明通道/调色板等各种来源）
    from PIL import Image
    with Image.open(src) as im:
        if im.mode != "RGB":
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        im.save(dest, format="JPEG", quality=95)
    log(f"   ✓ 已保存：{dest.name}")
    return str(dest)


def save_edit(data_bytes: bytes, ext: str = "png") -> str:
    """保存前端编辑器导出的图片。"""
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest = EDITS_DIR / f"edit_{ts}.{ext}"
    dest.write_bytes(data_bytes)
    return str(dest)


def inpaint(image_bytes: bytes, box: dict, prompt: str, log) -> str:
    """AI 局部重绘：裁剪带上下文的 tile → 模型重绘 → 羽化贴回，只改框选区域。"""
    import io
    import tempfile
    from PIL import Image, ImageDraw, ImageFilter

    im = Image.open(io.BytesIO(image_bytes))
    im = im.convert("RGB")
    W, H = im.size
    try:
        x, y = float(box.get("x", 0)), float(box.get("y", 0))
        w, h = float(box.get("w", 0.5)), float(box.get("h", 0.5))
    except (TypeError, ValueError):
        raise ValueError("box 坐标格式不正确")
    x = min(max(x, 0.0), 0.99)
    y = min(max(y, 0.0), 0.99)
    w = min(max(w, 0.02), 1 - x)
    h = min(max(h, 0.02), 1 - y)
    ax, ay = int(round(x * W)), int(round(y * H))
    aw, ah = int(round(w * W)), int(round(h * H))

    # 向外扩 30% 作为上下文，让模型知道周边环境；扩边部分不会被贴回
    mx, my = int(aw * 0.3), int(ah * 0.3)
    tx0, ty0 = max(0, ax - mx), max(0, ay - my)
    tx1, ty1 = min(W, ax + aw + mx), min(H, ah + ay + my)
    tile = im.crop((tx0, ty0, tx1, ty1))
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".jpg", prefix="inpaint_tile_")
    os.close(tmp_fd)
    tile_path = Path(tmp_name)
    try:
        tile.save(tile_path, format="JPEG", quality=95)
        prompt = (prompt or "").strip()
        if prompt:
            gen_prompt = (
                f"对这张局部画面进行重绘：{prompt}。保持与周围环境一致的画风、光影、色调与透视，"
                "新内容与画面边缘自然衔接，不要改变取景范围与构图"
            )
        else:
            gen_prompt = (
                "移除这张局部画面中的物体或人物，根据周围环境自然补全背景，延续原有纹理、透视、"
                "光影与色调，画面真实自然，不要留下任何编辑或抠图痕迹"
            )
        log(f"✨ AI 局部重绘：{prompt[:50] if prompt else '智能移除并补全背景'}")
        log(f"   选区 x={x:.2f} y={y:.2f} w={w:.2f} h={h:.2f}（{aw}×{ah}px）")
        gen_path = run_generator(gen_prompt, [str(tile_path)], "2K", log)

        with Image.open(gen_path) as g:
            gen = g.convert("RGB")
        # 缩回 tile 大小，再取出对应 inner 选区
        gen = gen.resize((tx1 - tx0, ty1 - ty0), Image.LANCZOS)
        ox, oy = ax - tx0, ay - ty0
        patch = gen.crop((ox, oy, ox + aw, oy + ah)).resize((aw, ah), Image.LANCZOS)

        # 边缘羽化，与原图无缝融合
        feather = max(4, int(min(aw, ah) * 0.04))
        mask = Image.new("L", (aw, ah), 0)
        d = ImageDraw.Draw(mask)
        d.rectangle((feather, feather, aw - feather, ah - feather), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
        im.paste(patch, (ax, ay), mask)
    finally:
        try:
            tile_path.unlink()
        except OSError:
            pass

    ts = time.strftime("%Y%m%d-%H%M%S")
    dest = GENERATED_DIR / f"inpaint_{ts}.jpg"
    im.save(dest, format="JPEG", quality=95)
    log(f"   ✓ 已保存：{dest.name}")
    return str(dest)


def save_upload(data: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in IMG_EXTS:
        ext = ".jpg"
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c for c in Path(filename).stem if c.isalnum() or c in "-_")[:20] or "img"
    dest = UPLOADS_DIR / f"upload_{ts}_{safe}{ext}"
    dest.write_bytes(data)
    return str(dest)


def gallery(limit: int = 100) -> dict:
    def items(d: Path) -> list[dict]:
        out = []
        if d.exists():
            for f in d.iterdir():
                if f.suffix.lower() in IMG_EXTS:
                    out.append({
                        "name": f.name,
                        "dir": next(k for k, v in DIR_MAP.items() if v == d),
                        "mtime": f.stat().st_mtime,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                    })
        out.sort(key=lambda x: x["mtime"], reverse=True)
        return out[:limit]
    return {"uploads": items(UPLOADS_DIR),
            "generated": items(GENERATED_DIR),
            "edits": items(EDITS_DIR)}
