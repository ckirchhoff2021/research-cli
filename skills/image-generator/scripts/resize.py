#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量把图片缩放/适配为标准尺寸并写入 DPI（如证件照一寸/二寸）。

比例一致时直接缩放；略有差异时等比缩放 + 用边缘色补边，不拉伸变形。

用法：
  python resize.py --images-dir outputs/.../images/阿哲 --out-dir outputs/.../print \
      --specs 一寸,二寸 --dpi 300
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# 常用证件/照片规格：slug -> (宽px, 高px, 宽mm, 高mm) @300dpi
SPECS = {
    "一寸": (295, 413, 25, 35),
    "小一寸": (260, 378, 22, 32),
    "大一寸": (390, 567, 33, 48),
    "二寸": (413, 579, 35, 49),
    "小二寸": (413, 531, 35, 45),
}


def fit_pad(im: Image.Image, w: int, h: int) -> Image.Image:
    im = im.convert("RGB")
    scale = min(w / im.width, h / im.height)
    nw, nh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    resized = im.resize((nw, nh), Image.LANCZOS)
    if (nw, nh) == (w, h):
        return resized
    pad_color = resized.getpixel((2, 2))
    canvas = Image.new("RGB", (w, h), pad_color)
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser(description="批量缩放为标准尺寸并写 DPI")
    ap.add_argument("--images-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--specs", default="一寸,二寸", help="逗号分隔：一寸/小一寸/大一寸/二寸/小二寸")
    ap.add_argument("--pattern", default="*.jpg")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--quality", type=int, default=95)
    args = ap.parse_args()

    names = [s.strip() for s in args.specs.split(",") if s.strip()]
    unknown = [s for s in names if s not in SPECS]
    if unknown:
        raise SystemExit(f"unknown specs: {unknown}, known={list(SPECS)}")

    it = args.images_dir.rglob(args.pattern) if args.recursive else args.images_dir.glob(args.pattern)
    files = sorted(p for p in it if p.is_file() and "contact" not in p.stem.lower())
    if not files:
        raise SystemExit(f"no images matched {args.pattern} in {args.images_dir}")

    n = 0
    for spec in names:
        w, h, mmw, mmh = SPECS[spec]
        spec_dir = args.out_dir / spec
        spec_dir.mkdir(parents=True, exist_ok=True)
        for p in files:
            with Image.open(p) as im:
                out = fit_pad(im, w, h)
            out.save(spec_dir / p.name, quality=args.quality, dpi=(args.dpi, args.dpi))
            n += 1
        print(f"{spec}: {len(files)} 张 -> {spec_dir} ({w}x{h}px = {mmw}x{mmh}mm @{args.dpi}dpi)")
    print(f"DONE: {n} files -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
