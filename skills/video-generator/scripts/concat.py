#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成长视频：统一规格 + 标题卡 + concat 拼接；系统 ffmpeg 坏时用 imageio-ffmpeg。

配合 batch.py scenes 产出的 scenes_manifest.json 使用：
  python concat.py --manifest clips/scenes_manifest.json \
      --output 长片.mp4 --title "阿哲的奇妙冒险" --cards
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = (
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
THEME_COLORS = {
    "01": (28, 78, 138),
    "02": (122, 62, 24),
    "03": (24, 96, 92),
    "04": (52, 44, 110),
    "05": (30, 30, 36),
}


def ffmpeg_works(exe: str) -> bool:
    try:
        proc = subprocess.run([exe, "-version"], capture_output=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe and ffmpeg_works(exe):
        return exe
    try:
        import imageio_ffmpeg  # type: ignore
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_works(bundled):
            return bundled
    except Exception:
        pass
    raise SystemExit("no working ffmpeg (system one is broken, imageio-ffmpeg unusable)")


def load_font(size: int):
    for fp in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def centered(draw, cy, text, font, fill, w):
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(((w - tw) / 2 - box[0], cy - th / 2 - box[1]), text, font=font, fill=fill)


def make_card(path: Path, big: str, small: str, theme_prefix: str, size):
    color = THEME_COLORS.get((theme_prefix or "")[:2], (24, 32, 48))
    w, h = size
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, 8), fill=(255, 200, 80))
    draw.rectangle((0, h - 8, w, h), fill=(255, 200, 80))
    if small:
        centered(draw, h / 2 - 90, small, load_font(42), (255, 214, 130), w)
    centered(draw, h / 2 + (16 if small else 0), big, load_font(70), (255, 255, 255), w)
    img.save(path, quality=92)


def has_audio(ffmpeg: str, video: Path) -> bool:
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", str(video)],
                          capture_output=True, text=True)
    return "Audio:" in proc.stderr


def encode_uniform(ffmpeg, src: Path, dst: Path, width, height, fps):
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if not has_audio(ffmpeg, src):
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
    cmd += ["-vf", vf, "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k",
            "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)


def card_to_video(ffmpeg, image: Path, dst: Path, duration, width, height, fps):
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-t", str(duration), "-i", str(image),
        "-f", "lavfi", "-t", str(duration), "-i", "anullsrc=r=48000:cl=stereo",
        "-vf", f"scale={width}:{height},setsar=1,fps={fps},format=yuv420p",
        "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k",
        "-shortest", str(dst),
    ], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="短视频列表合成长视频")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--clips-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="精彩合集")
    parser.add_argument("--cards", action="store_true")
    parser.add_argument("--card-duration", type=float, default=1.4)
    parser.add_argument("--intro-duration", type=float, default=2.6)
    parser.add_argument("--outro-duration", type=float, default=2.6)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--reencode-final", action="store_true")
    args = parser.parse_args()

    entries = []
    if args.manifest:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        for it in sorted(data, key=lambda x: x["idx"]):
            entries.append((Path(it["file"]), f"{it['idx']:02d} {it['title']}",
                            it["theme"], it["idx"]))
    elif args.clips_dir:
        files = sorted(p for p in args.clips_dir.rglob("*.mp4"))
        for i, p in enumerate(files, 1):
            entries.append((p, p.stem, p.parent.name, i))
    else:
        raise SystemExit("need --manifest or --clips-dir")
    missing = [str(p) for p, *_ in entries if not p.exists()]
    if missing:
        raise SystemExit(f"missing clips: {missing[:3]}")

    ffmpeg = find_ffmpeg()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="concat_") as tmpd:
        tmp = Path(tmpd)
        seq = []

        def add_card(big, small, theme_prefix, dur):
            n = len(seq)
            img = tmp / f"card_{n:03d}.jpg"
            vid = tmp / f"card_{n:03d}.mp4"
            make_card(img, big, small, theme_prefix, (args.width, args.height))
            card_to_video(ffmpeg, img, vid, dur, args.width, args.height, args.fps)
            seq.append(vid)

        add_card(args.title, "皮克斯角色场景合集", "00", args.intro_duration)
        last_theme = None
        for i, (clip, title, theme, _idx) in enumerate(entries):
            if args.cards:
                theme_name = theme.split("_", 1)[-1]
                if theme != last_theme:
                    add_card(theme_name, "— 本章 —", theme[:2], args.intro_duration)
                    last_theme = theme
                add_card(title, theme_name, theme[:2], args.card_duration)
            norm = tmp / f"clip_{i:03d}.mp4"
            print(f"[normalize {i + 1}/{len(entries)}] {clip.name}", flush=True)
            encode_uniform(ffmpeg, clip, norm, args.width, args.height, args.fps)
            seq.append(norm)
        add_card("未完待续", "感谢观看", "00", args.outro_duration)

        listfile = tmp / "list.txt"
        listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p in seq),
                            encoding="utf-8")
        print(f"[concat] {len(seq)} segments -> {args.output}", flush=True)
        if args.reencode_final:
            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                   "-f", "concat", "-safe", "0", "-i", str(listfile),
                   "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                   "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                   str(args.output)]
        else:
            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                   "-f", "concat", "-safe", "0", "-i", str(listfile),
                   "-c", "copy", "-movflags", "+faststart", str(args.output)]
        subprocess.run(cmd, check=True)

    print(f"DONE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
