"""最终合成：酷炫片头片尾 + 交叉淡入淡出 + 原始背景声 + 对白音轨精确对齐（无额外 BGM）。"""
from __future__ import annotations
import math
import os
import random
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy import VideoFileClip


# ── 画幅 → 目标像素 ───────────────────────────────────
DIM_MAP = {
    "16:9":  (1920, 1080),
    "9:16":  (1080, 1920),
    "1:1":   (1080, 1080),
    "3:4":   (1080, 1440),
    "4:3":   (1440, 1080),
    "21:9":  (1920, 824),
}


def target_dims(project: dict) -> tuple[int, int]:
    ratio = project.get("ratio", "9:16")
    return DIM_MAP.get(ratio, (1080, 1920))


# ── 酷炫片头卡片（PIL 精绘） ─────────────────────────
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _font(size: int):
    for fp in FONT_CANDIDATES:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _radial_glow(size, inner, outer, cx=0.5, cy=0.42):
    """径向渐变光晕：inner 为中心 RGBA，向外过渡到透明。"""
    import numpy as np
    w, h = size
    maxr = math.hypot(max(cx, 1 - cx) * w, max(cy, 1 - cy) * h)
    ir, ig, ib, ia = inner
    xs = (np.arange(w)[None, :] / w - cx) * w
    ys = (np.arange(h)[:, None] / h - cy) * h
    d = np.minimum(1.0, np.hypot(xs, ys) / maxr)
    a = (ia * (1 - d) ** 2).astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0] = ir; arr[..., 1] = ig; arr[..., 2] = ib; arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


def _text_size(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def _fit_font(text, max_w, start, min_size=40):
    size = start
    while size > min_size:
        f = _font(size)
        tmp = Image.new("RGB", (10, 10))
        if _text_size(ImageDraw.Draw(tmp), text, f)[0] <= max_w:
            return f
        size -= 4
    return _font(min_size)


def draw_title_art(project: dict, W: int, H: int) -> Image.Image:
    """绘制电影感片头：纯黑底 + 金色尘粒 + 金色标题发光。"""
    import numpy as np
    random.seed(20261029)
    script = project.get("script", {})
    title = script.get("title", project.get("name", "短剧"))
    genre = script.get("genre", "")
    logline = script.get("logline", "")

    # 纯黑背景
    img = Image.new("RGB", (W, H), (0, 0, 0))

    # 金色尘粒
    draw = ImageDraw.Draw(img, "RGBA")
    for _ in range(int(W * H / 22000)):
        x, y = random.randint(0, W - 1), random.randint(0, H - 1)
        r = random.choice([1, 1, 1, 2, 2, 3])
        a = random.randint(70, 210)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(242, 201, 120, a))

    # 四角装饰线
    m, L, lw = int(W * 0.07), int(W * 0.05), 3
    gold = (242, 201, 120, 200)
    for (x0, y0, sx, sy) in [
        (m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)
    ]:
        draw.line([(x0, y0), (x0 + sx * L, y0)], fill=gold, width=lw)
        draw.line([(x0, y0), (x0, y0 + sy * L)], fill=gold, width=lw)

    cx = W / 2
    # genre 小标签
    f_small = _fit_font(genre, int(W * 0.7), 30, 20) if genre else None
    title_y = H * 0.40
    if f_small and genre:
        tw, th = _text_size(draw, genre, f_small)
        draw.text((cx - tw / 2, title_y - th - H * 0.045), genre,
                  fill=(214, 198, 160, 255), font=f_small)

    # 标题：发光层（模糊）+ 描边 + 金色主体
    f_title = _fit_font(title, int(W * 0.82), int(W * 0.115), 46)
    tw, th = _text_size(draw, title, f_title)
    tx, ty = cx - tw / 2, title_y
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text((tx, ty), title, font=f_title, fill=(255, 210, 120, 230))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img = img.convert("RGBA")
    img.alpha_composite(glow)
    draw = ImageDraw.Draw(img)
    for ox, oy in [(-3, 0), (3, 0), (0, -3), (0, 3)]:
        draw.text((tx + ox, ty + oy), title, font=f_title, fill=(90, 55, 15, 255))
    draw.text((tx, ty), title, font=f_title, fill=(246, 214, 140, 255))
    base = img

    # 标题下金色分隔线 + 菱形
    draw = ImageDraw.Draw(base)
    ly = ty + th + H * 0.045
    half = int(W * 0.13)
    draw.line([(cx - half, ly), (cx - 14, ly)], fill=(242, 201, 120, 230), width=2)
    draw.line([(cx + 14, ly), (cx + half, ly)], fill=(242, 201, 120, 230), width=2)
    d = 7
    draw.polygon([(cx, ly - d), (cx + d, ly), (cx, ly + d), (cx - d, ly)],
                 fill=(242, 201, 120, 255))

    # logline
    if logline:
        f_log = _fit_font(logline, int(W * 0.76), 30, 20)
        tw, _ = _text_size(draw, logline, f_log)
        draw.text((cx - tw / 2, ly + 26), logline,
                  fill=(225, 220, 208, 235), font=f_log)
    return base.convert("RGB")


def draw_end_art(project: dict, W: int, H: int) -> Image.Image:
    """片尾卡片：纯黑底 + 剧终。"""
    random.seed(7)
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = _fit_font("剧 终", int(W * 0.6), int(W * 0.13), 46)
    tw, th = _text_size(draw, "剧 终", f)
    cx, cy = W / 2, H / 2
    draw.text((cx - tw / 2, cy - th / 2), "剧 终", font=f, fill=(246, 214, 140))
    half = int(W * 0.12)
    draw.line([(cx - half, cy + th), (cx - 12, cy + th)], fill=(242, 201, 120), width=2)
    draw.line([(cx + 12, cy + th), (cx + half, cy + th)], fill=(242, 201, 120), width=2)
    return img


def _sweep_png(path: str):
    """对角光扫条：白色 + alpha 渐变。"""
    import numpy as np
    w, h = 360, 1080
    band = 130
    xs = np.arange(w)[None, :]
    ys = np.arange(h)[:, None]
    d = np.abs(xs - w / 2) / (band / 2)
    a = np.where(d < 1, (150 * (1 - np.minimum(d, 1)) ** 2), 0).astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., 0] = 255; arr[..., 1] = 250; arr[..., 2] = 235; arr[..., 3] = a
    im = Image.fromarray(arr, "RGBA").rotate(25, resample=Image.BILINEAR, expand=True)
    im.save(path)


def make_card(ff, out, art: Image.Image, dur, W, H, FPS,
              zoom_end=1.10, sweep: str | None = None):
    """静态精绘卡片 → Ken Burns 缓推 + 淡入淡出（片头再加光扫）。"""
    png = os.path.join(tempfile.gettempdir(), f"_card_{os.path.basename(out)}.png")
    art.save(png)
    frames = int(dur * FPS)
    zexpr = f"'min(1+({zoom_end}-1)*on/{frames},{zoom_end})'"
    vf = (
        f"zoompan=z={zexpr}:x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
        f":d={frames}:s={W}x{H}:fps={FPS},"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st={dur-0.6:.2f}:d=0.6"
    )
    cmd = [ff, "-y", "-loop", "1", "-i", png]
    if sweep:
        cmd += ["-i", sweep]
    cmd += ["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo"]
    if sweep:
        travel = W + 900
        vf = (
            f"[0:v]{vf}[base];"
            f"[base][1:v]overlay=x='-450+(t-0.4)*{travel/2.2:.0f}':y='(H-h)/2'"
            f":enable='between(t,0.5,2.7)':format=auto[v]"
        )
        cmd += ["-filter_complex", vf, "-map", "[v]", "-map", "2:a"]
    else:
        cmd += ["-vf", vf, "-map", "0:v", "-map", "1:a"]
    cmd += ["-t", str(dur), "-r", str(FPS), "-c:v", "libx264", "-preset", "fast",
            "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-shortest", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0


def _has_audio(ff, path) -> bool:
    r = subprocess.run([ff, "-i", path], capture_output=True, text=True)
    return "Audio:" in r.stderr


def compose_final(project, base, venv_py, ff, project_root):
    WK = tempfile.mkdtemp(prefix="dc_compose_")
    W, H = target_dims(project)
    FPS = 24

    def run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  [ERR] {r.stderr[-400:]}")
            return False
        return True

    def vdur(p):
        c = VideoFileClip(p)
        d = c.duration
        c.close()
        return d

    # 片段顺序严格以 project["shots"] 为准（文件按 uid 命名，不能靠 glob）
    shot_files = []
    for shot in project.get("shots", []):
        vf = shot.get("video_file", "")
        if vf and os.path.exists(vf):
            shot_files.append(vf)
    if not shot_files:
        raise RuntimeError("没有可合成的视频片段，请先生成视频")

    print("[1] 规范化视频片段（保持原比例，不变形）...")
    nps = []
    for i, sp in enumerate(shot_files):
        o = os.path.join(WK, f"n{i:02d}.mp4")
        d = vdur(sp)
        fo = 4 if i == len(shot_files) - 1 else 0
        # cover 缩放：先等比放大铺满，再中心裁切到目标尺寸；视频本身即目标比例时等于无操作
        vf = [
            f"scale={W}:{H}:force_original_aspect_ratio=increase",
            f"crop={W}:{H}",
            "setsar=1", "format=yuv420p", f"fps={FPS}",
        ]
        af = []
        if fo:
            vf.append(f"fade=out:{int((d-fo)*FPS)}:{int(fo*FPS)}")
            af.append(f"afade=t=out:st={d-fo}:d={fo}")
        cmd = [ff, "-y"]
        if _has_audio(ff, sp):
            cmd += ["-i", sp, "-vf", ",".join(vf)]
            if af:
                cmd += ["-af", ",".join(af)]
        else:
            # 无原声的片段补静音轨，保证 acrossfade 链路完整
            cmd += ["-i", sp, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-vf", ",".join(vf), "-map", "0:v", "-map", "1:a"]
        cmd += ["-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", o]
        print(f"  {os.path.basename(sp)}...", end=" ", flush=True)
        print("OK" if run(cmd) else "FAIL")
        nps.append(o)

    print("\n[2] 片头片尾...")
    tp = os.path.join(WK, "t.mp4")
    ep = os.path.join(WK, "e.mp4")
    sweep = os.path.join(WK, "sweep.png")
    _sweep_png(sweep)
    title_art = draw_title_art(project, W, H)
    end_art = draw_end_art(project, W, H)
    if not make_card(ff, tp, title_art, 3.2, W, H, FPS, zoom_end=1.08, sweep=sweep):
        raise RuntimeError("片头卡片生成失败，请检查 ffmpeg 滤镜参数")
    if not make_card(ff, ep, end_art, 4.5, W, H, FPS, zoom_end=1.05):
        raise RuntimeError("片尾卡片生成失败，请检查 ffmpeg 滤镜参数")

    clips = [tp] + nps + [ep]
    durs = [vdur(p) for p in clips]
    xfd = [0.8] + [0.6] * len(nps) + [0.8]

    print("\n[3] 拼接视频（acrossfade 保留原始背景声）...")
    offs = []
    cum = durs[0]
    for i in range(1, len(clips)):
        offs.append(cum - xfd[i - 1])
        cum += durs[i] - xfd[i - 1]
    td = cum
    inputs = []
    for p in clips:
        inputs += ["-i", p]
    fl = []
    pv, pa = "0:v", "0:a"
    for i in range(1, len(clips)):
        ov = f"v{i}" if i < len(clips) - 1 else "vo"
        oa = f"a{i}" if i < len(clips) - 1 else "ao"
        fl.append(f"[{pv}][{i}:v]xfade=transition=fade:duration={xfd[i-1]}"
                   f":offset={offs[i-1]:.3f}[{ov}]")
        fl.append(f"[{pa}][{i}:a]acrossfade=d={xfd[i-1]}:c1=tri:c2=tri[{oa}]")
        pv, pa = ov, oa
    cp = os.path.join(WK, "cat.mp4")
    run([ff, "-y"] + inputs + ["-filter_complex", ";".join(fl),
        "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-r", str(FPS), cp])

    print("\n[4] 最终合成（直接保留视频原始音频，不叠加配音/BGM）...")
    final_path = str(base / "final.mp4")
    if os.path.exists(final_path):
        os.remove(final_path)
    # cat.mp4 已含各片段原始音频的 acrossfade 混音，直接重封装即可
    run([ff, "-y", "-i", cp, "-c", "copy", "-shortest", final_path])

    if os.path.exists(final_path):
        sz = os.path.getsize(final_path) / (1024 * 1024)
        c = VideoFileClip(final_path)
        print(f"\n✅ 成片完成: {final_path}")
        print(f"   时长: {c.duration:.1f}s, {c.size[0]}x{c.size[1]}, {sz:.1f}MB")
        c.close()
        project["final_video"] = final_path
