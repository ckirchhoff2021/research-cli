#!/usr/bin/env python3
"""确定性超分辨率：只提高清晰度，不重绘、不改变任何五官。

与生成式模型（Seedream）不同，本工具用 Real-ESRGAN CoreML 卷积网络做逐块超分：
几何与身份信息逐像素保持，只增强对焦与细节。固定 512x512 输入 -> 2048x2048 输出，
自动分块 + overlap 羽化加权，输出 4x 大图，并缩回一份「原尺寸增强版」。

用法：
  .venv/bin/python skills/image-generator/scripts/superres.py \
    --image outputs/.../photo.jpg --out-dir outputs/.../超分
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
MODEL_PATH = SKILL_DIR / "models" / "coreml" / "RealESRGAN.mlmodel"


def tile_origins(length: int, tile: int, stride: int) -> list[int]:
    """从 0 起按 stride 铺 tile，最后一个贴边回退，保证全部落在 [0,length]。"""
    if length <= tile:
        return [0]
    pts = list(range(0, length - tile, stride))
    pts.append(length - tile)
    out = []
    for p in pts:  # 去重并保序
        if not out or p != out[-1]:
            out.append(p)
    return out


def feather(tile_out: int, overlap_out: int, x: int, y: int,
            out_w: int, out_h: int) -> np.ndarray:
    """tile 权重：overlap 区域内 0->1 渐变；贴图像边缘的一侧直接为 1。"""
    w = np.ones(tile_out, np.float32)
    ramp = np.linspace(0, 1, overlap_out, dtype=np.float32)
    left, top = x * 4, y * 4
    right, bottom = left + tile_out, top + tile_out
    if left > 0:
        w[:overlap_out] = ramp
    if right < out_w:
        w[-overlap_out:] = ramp[::-1]
    h = np.ones(tile_out, np.float32)
    if top > 0:
        h[:overlap_out] = ramp
    if bottom < out_h:
        h[-overlap_out:] = ramp[::-1]
    return w[None, :] * h[:, None]


def usm(rgb: np.ndarray, amount: float, radius: float) -> np.ndarray:
    import cv2
    blurred = cv2.GaussianBlur(rgb, (0, 0), radius)
    return np.clip(rgb.astype(np.float32) * (1 + amount) - blurred.astype(np.float32) * amount,
                   0, 255).astype(np.uint8)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="确定性超分：只提高清晰度，不改五官")
    p.add_argument("--image", required=True, type=Path)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--tile", type=int, default=512)
    p.add_argument("--overlap", type=int, default=64, help="输入像素，默认64（输出256）")
    p.add_argument("--compute-unit", choices=["all", "cpu", "gpu", "ane"], default="all")
    p.add_argument("--usm", type=float, default=0.15, help="额外锐化强度，默认0.15")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    import coremltools as ct

    src = ImageOps.exif_transpose(Image.open(args.image)).convert("RGB")
    W, H = src.size
    stride = args.tile - args.overlap
    xs = tile_origins(W, args.tile, stride)
    ys = tile_origins(H, args.tile, stride)
    out_w, out_h = W * 4, H * 4
    print(f"tiles={len(xs)*len(ys)} ({len(xs)}x{len(ys)}) -> {out_w}x{out_h}", flush=True)

    cu = {"all": ct.ComputeUnit.ALL, "cpu": ct.ComputeUnit.CPU_ONLY,
          "gpu": ct.ComputeUnit.CPU_AND_GPU, "ane": ct.ComputeUnit.CPU_AND_NE}[args.compute_unit]
    model = ct.models.MLModel(str(MODEL_PATH), compute_units=cu)

    acc = np.zeros((out_h, out_w, 3), np.float32)
    wsum = np.zeros((out_h, out_w), np.float32)
    src_np = np.asarray(src)
    t0 = time.time()
    total = len(xs) * len(ys)
    n = 0
    for y in ys:
        for x in xs:
            patch = src_np[y:y + args.tile, x:x + args.tile]
            if patch.shape[0] < args.tile or patch.shape[1] < args.tile:
                # 理论上贴边回退已避免，保险起见 reflect 补齐
                ph, pw = patch.shape[:2]
                patch = np.pad(patch, ((0, args.tile - ph), (0, args.tile - pw), (0, 0)), mode="reflect")
            pil = Image.fromarray(patch)
            out = model.predict({"input": pil})["activation_out"].convert("RGB")
            tile = np.asarray(out, np.float32)
            wt = feather(args.tile * 4, args.overlap * 4, x, y, out_w, out_h)
            ox, oy = x * 4, y * 4
            acc[oy:oy + args.tile * 4, ox:ox + args.tile * 4] += tile * wt[..., None]
            wsum[oy:oy + args.tile * 4, ox:ox + args.tile * 4] += wt
            n += 1
            if n % 4 == 0 or n == total:
                print(f"  {n}/{total}  {time.time()-t0:.0f}s", flush=True)

    final = np.clip(acc / np.maximum(wsum[..., None], 1e-6), 0, 255).astype(np.uint8)
    if args.usm > 0:
        final = usm(final, args.usm, 1.2)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.image.stem
    big_path = args.out_dir / f"{stem}_超分4x.jpg"
    Image.fromarray(final).save(big_path, quality=95, dpi=(300, 300))

    native = Image.fromarray(final).resize((W, H), Image.LANCZOS)
    native_path = args.out_dir / f"{stem}_超分_原尺寸.jpg"
    native.save(native_path, quality=95, dpi=(300, 300))

    import cv2
    gray_o = cv2.cvtColor(src_np, cv2.COLOR_RGB2GRAY)
    gray_n = cv2.cvtColor(np.asarray(native), cv2.COLOR_RGB2GRAY)
    print(json.dumps({
        "laplacian_original": round(float(cv2.Laplacian(gray_o, cv2.CV_32F).var()), 2),
        "laplacian_native": round(float(cv2.Laplacian(gray_n, cv2.CV_32F).var()), 2),
        "big": str(big_path), "native": str(native_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
