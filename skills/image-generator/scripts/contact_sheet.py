#!/usr/bin/env python3
"""通用联系表（contact sheet）生成工具：把一个目录里的图片拼成网格总览。

示例：
  python contact_sheet.py --images-dir outputs/x/images --output outputs/x/sheet.jpg --cols 5
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = (
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
SKIP_KEYWORDS = ("contact", "sheet", "联系表", "总览")


def natural_key(path: Path):
    parts = re.split(r"(\d+)", path.stem)
    return [int(p) if p.isdigit() else p for p in parts]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for fp in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def collect(images_dir: Path, pattern: str, recursive: bool) -> list[Path]:
    it = images_dir.rglob(pattern) if recursive else images_dir.glob(pattern)
    images = [p for p in it if p.is_file()
              and not any(k in p.stem.lower() for k in SKIP_KEYWORDS)]
    return sorted(images, key=natural_key)


def main() -> int:
    parser = argparse.ArgumentParser(description="把目录图片拼成联系表")
    parser.add_argument("--images-dir", required=True, type=Path)
    parser.add_argument("--output", default=None, type=Path,
                        help="输出路径，默认 images-dir/contact_sheet.jpg")
    parser.add_argument("--pattern", default="*.jpg")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--cols", type=int, default=5)
    parser.add_argument("--cell-w", type=int, default=360)
    parser.add_argument("--cell-h", type=int, default=640)
    parser.add_argument("--pad", type=int, default=12)
    parser.add_argument("--label", choices=("auto", "none"), default="auto")
    parser.add_argument("--font-size", type=int, default=20)
    parser.add_argument("--quality", type=int, default=88)
    args = parser.parse_args()

    images = collect(args.images_dir, args.pattern, args.recursive)
    if not images:
        raise SystemExit(f"no images matched {args.pattern} in {args.images_dir}")

    rows = (len(images) + args.cols - 1) // args.cols
    label_h = args.font_size + 18 if args.label == "auto" else 0
    width = args.cols * args.cell_w + (args.cols + 1) * args.pad
    height = rows * (args.cell_h + label_h) + (rows + 1) * args.pad
    sheet = Image.new("RGB", (width, height), (245, 245, 248))
    draw = ImageDraw.Draw(sheet)
    font = load_font(args.font_size)

    for i, path in enumerate(images):
        r, c = divmod(i, args.cols)
        x = args.pad + c * (args.cell_w + args.pad)
        y = args.pad + r * (args.cell_h + label_h + args.pad)
        with Image.open(path) as im:
            im = im.convert("RGB")
            scale = max(args.cell_w / im.width, args.cell_h / im.height)
            im = im.resize((int(im.width * scale), int(im.height * scale)))
            left = (im.width - args.cell_w) // 2
            top = (im.height - args.cell_h) // 2
            sheet.paste(im.crop((left, top, left + args.cell_w, top + args.cell_h)), (x, y))
        if args.label == "auto":
            draw.text((x + 6, y + args.cell_h + 8), path.stem, fill=(40, 40, 50), font=font)

    output = args.output or (args.images_dir / "contact_sheet.jpg")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=args.quality)
    print(f"Saved contact sheet: {output} ({len(images)} images, {rows}x{args.cols})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
