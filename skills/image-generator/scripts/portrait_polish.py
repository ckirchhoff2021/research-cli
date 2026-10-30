#!/usr/bin/env python3
"""人像精修：高清修复 / 轻度自然美颜，并强制保证构图零裁剪。

流程：
  1. res10 SSD 人脸框 + 眼镜专用 Haar 级联定位原图/成图双眼；
  2. 按模式（restore/beautify）调用 Seedream 图生图，提示词带「构图锁定」；
  3. 量化构图偏差（人物缩放 scale + 双眼中心位移 dx/dy），不合格带纠正指令重跑；
  4. 用相似变换把最佳成图对齐到原图双眼坐标（任意分辨率下取景与原片完全一致）；
  5. 同时导出原尺寸版与高清版（默认 4K），并生成左右对比图供目检。

示例：
  .venv/bin/python skills/image-generator/scripts/portrait_polish.py \
    --image outputs/.../photo.jpg --mode beautify --size 4K
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageOps
from dotenv import load_dotenv

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2  # noqa: E402
from generator import ImageGenerator  # noqa: E402

CONFIG_PATH = SKILL_DIR / "presets" / "portrait-polish.json"

# Seedream 尺寸 -> 导出长边（保持原图宽高比）
SIZE_LONG_EDGE = {"2K": 2464, "3K": 3520, "4K": 4704}


class FaceEngine:
    """SSD 人脸框 + 戴眼镜可用的眼睛级联（模型文件随技能分发）。"""

    def __init__(self) -> None:
        m = SKILL_DIR / "models"
        self.net = cv2.dnn.readNetFromCaffe(
            str(m / "deploy.prototxt"), str(m / "res10.caffemodel")
        )
        self.eyes = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
        )

    def face_box(self, rgb: np.ndarray) -> tuple[int, int, int, int]:
        h, w = rgb.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(rgb, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0)
        )
        self.net.setInput(blob)
        det = self.net.forward()
        best = None
        for i in range(det.shape[2]):
            if float(det[0, 0, i, 2]) >= 0.6:
                x1, y1, x2, y2 = det[0, 0, i, 3:7] * np.array([w, h, w, h])
                area = max(0, x2 - x1) * max(0, y2 - y1)
                if best is None or area > best[0]:
                    best = (area, (int(x1), int(y1), int(x2), int(y2)))
        if best is None:
            raise RuntimeError("未检测到人脸")
        return best[1]

    def eye_points(self, rgb: np.ndarray) -> np.ndarray:
        """返回画面从左到右两眼中心 (2,2)；级联失败按脸框比例兜底。"""
        h, w = rgb.shape[:2]
        x1, y1, x2, y2 = self.face_box(rgb)
        bw, bh = x2 - x1, y2 - y1
        px, py = int(0.10 * w), int(0.06 * h)
        cx1, cy1 = max(0, x1 - px), max(0, y1 - py)
        cx2, cy2 = min(w, x2 + px), min(h, y2 + int(0.18 * h))
        gray = cv2.cvtColor(rgb[cy1:cy2, cx1:cx2], cv2.COLOR_RGB2GRAY)
        found = self.eyes.detectMultiScale(
            gray, 1.05, 4, minSize=(max(20, int(0.09 * w)), max(15, int(0.06 * h)))
        )
        centers = np.array([[cx1 + ex + ew / 2, cy1 + ey + eh / 2]
                            for ex, ey, ew, eh in found], dtype=np.float64)
        pair = None
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                a, b = centers[i], centers[j]
                gap, level = abs(a[0] - b[0]), abs(a[1] - b[1])
                if level < 0.035 * h and 0.30 * bw < gap < 0.95 * bw:
                    score = gap - level * 3 - max(a[1], b[1]) * 0.01
                    if pair is None or score > pair[0]:
                        pair = (score, np.array([a, b]))
        if pair is not None:
            pts = pair[1]
            return pts[np.argsort(pts[:, 0])]
        return np.array([[x1 + 0.31 * bw, y1 + 0.40 * bh],
                         [x1 + 0.69 * bw, y1 + 0.40 * bh]], dtype=np.float64)


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))


def load_rgb_from_url(url: str) -> np.ndarray:
    data = requests.get(url, timeout=180).content
    if len(data) < 20 * 1024:
        raise RuntimeError("下载图像过小")
    return np.asarray(Image.open(BytesIO(data)).convert("RGB"))


def edge_background(rgb: np.ndarray) -> tuple[int, int, int]:
    """取四条边缘条带的中位数作为背景填充色。"""
    s = 60
    strips = [rgb[:s, :].reshape(-1, 3), rgb[-s:, :].reshape(-1, 3),
              rgb[:, :s].reshape(-1, 3), rgb[:, -s:].reshape(-1, 3)]
    med = np.median(np.vstack(strips), axis=0)
    return tuple(int(v) for v in med)


def padded_canvas(rgb: np.ndarray, k: float) -> Image.Image:
    """把原图居中放到 k 倍大、同背景色的画布上（预补偿模型爱推近的问题）。"""
    h, w = rgb.shape[:2]
    W, H = round(w * k), round(h * k)
    canvas = Image.new("RGB", (W, H), edge_background(rgb))
    canvas.paste(Image.fromarray(rgb), (round((W - w) / 2), round((H - h) / 2)))
    return canvas


def framing_error(engine: FaceEngine, orig: np.ndarray, cand: np.ndarray,
                  eo: np.ndarray) -> tuple[float, dict]:
    """归一化构图偏差：scale=人物大小比，dx/dy=双眼中心位移（占原图宽/高）。"""
    ho, wo = orig.shape[:2]
    hc, wc = cand.shape[:2]
    ec = engine.eye_points(cand)
    do = np.linalg.norm(eo[1] - eo[0]) / wo
    dc = np.linalg.norm(ec[1] - ec[0]) / wc
    mo, mc = eo.mean(axis=0) / [wo, ho], ec.mean(axis=0) / [wc, hc]
    dx, dy = mc - mo
    score = max(abs(dc / do - 1.0), abs(dx) * 2.0, abs(dy) * 2.0)
    return score, {"scale": dc / do, "dx": float(dx), "dy": float(dy)}


def build_prompt(cfg: dict, mode: str, extra: list[str]) -> str:
    m = cfg["modes"][mode]
    parts = [m["prompt"], cfg["framing_lock"], cfg["identity_lock"]] + extra
    return "。".join(p.rstrip("。") for p in parts) + "。"


def correction_hints(err: dict, cfg: dict) -> list[str]:
    c = cfg["corrections"]
    hints = []
    if err["scale"] > 1.02:
        hints.append(c["zoom_out"])
    elif err["scale"] < 0.98:
        hints.append(c["zoom_in"])
    if err["dx"] > 0.01:
        hints.append(c["move_left"])
    elif err["dx"] < -0.01:
        hints.append(c["move_right"])
    if err["dy"] > 0.01:
        hints.append(c["move_up"])
    elif err["dy"] < -0.01:
        hints.append(c["move_down"])
    return hints or [c["retry"]]


def align_warp(engine: FaceEngine, orig: np.ndarray, cand: np.ndarray,
               orig_eyes: np.ndarray, canvas_wh: tuple[int, int]) -> np.ndarray:
    """相似变换对齐双眼到原构图；返回 (RGB图, 有效覆盖mask)。"""
    ho, wo = orig.shape[:2]
    W, H = canvas_wh
    target = orig_eyes / [wo, ho] * [W, H]
    source = engine.eye_points(cand)
    mat = similarity_mat(source, target)
    warped = cv2.warpAffine(
        cv2.cvtColor(cand, cv2.COLOR_RGB2BGR), mat, (W, H),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )
    cover = cv2.warpAffine(np.ones(cand.shape[:2], np.float32), mat, (W, H),
                           flags=cv2.INTER_NEAREST, borderValue=0)
    return cv2.cvtColor(warped, cv2.COLOR_BGR2RGB), cover


def similarity_mat(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    vs, vt = source[1] - source[0], target[1] - target[0]
    scale = float(np.hypot(*vt) / np.hypot(*vs))
    ang = float(np.arctan2(vt[1], vt[0]) - np.arctan2(vs[1], vs[0]))
    rot = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    shift = target.mean(axis=0) - scale * rot @ source.mean(axis=0)
    return np.hstack([scale * rot, shift.reshape(2, 1)]).astype(np.float64)


def composite(engine: FaceEngine, orig: np.ndarray, cand: np.ndarray,
              canvas_wh: tuple[int, int]) -> np.ndarray:
    """兜底合成：美颜成图对齐双眼，羽化融入放大增强后的原片，保证零裁剪。"""
    W, H = canvas_wh
    base = cv2.resize(orig, (W, H), interpolation=cv2.INTER_LANCZOS4)
    base = cv2.GaussianBlur(base, (0, 0), 0.6)
    base = cv2.addWeighted(cv2.resize(orig, (W, H), interpolation=cv2.INTER_LANCZOS4),
                           1.6, base, -0.6, 0)  # 轻量反模糊
    warped, cover = align_warp(engine, orig, cand,
                               engine.eye_points(orig), canvas_wh)
    x1, y1, x2, y2 = engine.face_box(orig)
    oh, ow = orig.shape[:2]
    cx, cy = (x1 + x2) / 2 / ow * W, (y1 + y2) / 2 / oh * H
    rx = (x2 - x1) / ow * W * 0.62          # 覆盖双颊
    ry = (y2 - y1) / oh * H * 0.78 + 0.05 * H  # 额头到下巴
    cy -= 0.02 * H
    mask = np.zeros((H, W), np.float32)
    cv2.ellipse(mask, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, 1, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), W * 0.02) * cover
    m = mask[..., None]
    out = (warped.astype(np.float32) * m + base.astype(np.float32) * (1 - m))
    return np.clip(out, 0, 255).astype(np.uint8)


def compare_sheet(orig: np.ndarray, final_hd: np.ndarray, path: Path) -> None:
    h = 1200
    a = Image.fromarray(orig); a.thumbnail((h, h))
    b = Image.fromarray(final_hd); b.thumbnail((h, h))
    H = max(a.height, b.height)
    sheet = Image.new("RGB", (a.width + b.width + 24, H), (240, 240, 240))
    sheet.paste(a, (0, 0)); sheet.paste(b, (a.width + 24, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=90)


def run_collect(args: argparse.Namespace, cfg: dict, engine: "FaceEngine",
                gen: "ImageGenerator", orig: np.ndarray, orig_eyes: np.ndarray,
                out_dir: Path) -> int:
    """批量直出：纯 Seedream 整图生成 N 次，原样保留构图达标的成图，不对齐不合成。"""
    from PIL import ImageDraw
    oh, ow = orig.shape[:2]
    k_max = float(np.sqrt(36_000_000 * 0.96 / (ow * oh)))
    cand_dir = out_dir / "直出候选"
    cand_dir.mkdir(parents=True, exist_ok=True)
    mode_name = cfg["modes"][args.mode]["name"]
    prompt = build_prompt(cfg, args.mode, [
        "参考图人物四周保留有大面积纯色背景留白，成图取景必须与参考图的留白比例一致，"
        "不要把人物放大填满画面、不要推近裁切。"])

    saved: list[tuple[Path, float]] = []
    k_choices = [min(x, k_max) for x in
                 (args.pad_scale, 3.0, 2.9, 3.05, 2.85, args.pad_scale * 0.95)]
    for i in range(1, args.collect + 1):
        k = k_choices[(i - 1) % len(k_choices)]
        canvas = padded_canvas(orig, k)
        print(f"[collect {i}/{args.collect}] 生成中…（k={k:.2f}）", flush=True)
        try:
            url = gen.text2image(prompt, args.size, canvas)
            cand = load_rgb_from_url(url)
        except Exception as exc:  # noqa: BLE001
            print(f"[collect {i}] 失败：{str(exc)[:120]}", flush=True)
            continue
        score, err = framing_error(engine, orig, cand, orig_eyes)
        print(f"[collect {i}] 偏差={score:.3f} (scale={err['scale']:.3f}, "
              f"dx={err['dx']:+.3f}, dy={err['dy']:+.3f})", flush=True)
        if score <= args.tolerance:
            existing = len(list(cand_dir.glob(f"{mode_name}_直出*.jpg")))
            path = cand_dir / f"{mode_name}_直出{existing+1:02d}_偏差{score:.3f}.jpg"
            Image.fromarray(cand).save(path, quality=95, dpi=(300, 300))
            saved.append((path, score))

    all_paths = sorted(cand_dir.glob(f"{mode_name}_直出*.jpg"))
    if all_paths:
        thumbs = []
        for path in all_paths:
            im = Image.open(path).convert("RGB")
            im.thumbnail((560, 760))
            tile = Image.new("RGB", (im.width, im.height + 36), (255, 255, 255))
            tile.paste(im, (0, 36))
            d = ImageDraw.Draw(tile)
            d.text((8, 8), "_".join(path.stem.split("_")[-2:]), fill=(200, 0, 0))
            thumbs.append(tile)
        cols = min(4, len(thumbs) + 1)
        rows = (len(thumbs) + 1 + cols - 1) // cols
        cw, ch = 560, 800
        sheet = Image.new("RGB", (cols * cw, rows * ch), (235, 235, 235))
        o = Image.fromarray(orig); o.thumbnail((560, 760))
        ot = Image.new("RGB", (o.width, o.height + 36), (255, 255, 255))
        ot.paste(o, (0, 36))
        ImageDraw.Draw(ot).text((8, 8), "原片", fill=(0, 120, 0))
        tiles = [ot] + thumbs
        for idx, t in enumerate(tiles):
            sheet.paste(t, ((idx % cols) * cw + 10, (idx // cols) * ch + 10))
        sheet_path = out_dir / f"_直出候选总览_{mode_name}.jpg"
        sheet.save(sheet_path, quality=88)
    else:
        sheet_path = None

    print(json.dumps({
        "passes": len(saved), "total_candidates": len(all_paths),
        "attempts": args.collect,
        "candidates": [str(p) for p, _ in saved],
        "contact_sheet": str(sheet_path) if sheet_path else None,
    }, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="人像精修：高清修复/自然美颜，构图零裁剪")
    p.add_argument("--image", required=True, type=Path)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--mode", choices=["restore", "beautify"], default="beautify")
    p.add_argument("--size", choices=["2K", "3K", "4K"], default="4K")
    p.add_argument("--max-tries", type=int, default=4)
    p.add_argument("--tolerance", type=float, default=0.03)
    p.add_argument("--pad-scale", type=float, default=3.0,
                   help="白边预补偿倍数（模型默认会把人物放大约3倍，默认3.0）")
    p.add_argument("--collect", type=int, default=0,
                   help="批量直出模式：跑 N 次纯 Seedream 整图生成，保留所有构图达标的原片，"
                        "不做相似变换对齐、不做合成兜底（用于挑选形变最小的一张）")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    orig = load_rgb(args.image)
    oh, ow = orig.shape[:2]
    engine = FaceEngine()
    orig_eyes = engine.eye_points(orig)

    out_dir = args.out_dir or (REPO_ROOT / "outputs" / "人像精修")
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = ImageGenerator(
        base_url=os.getenv("IMAGE_GEN_BASE_URL"),
        api_key=os.getenv("IMAGE_GEN_API_KEY"),
        model_name=os.getenv("IMAGE_GEN_MODEL"),
    )

    if args.collect > 0:
        return run_collect(args, cfg, engine, gen, orig, orig_eyes, out_dir)

    extra: list[str] = []
    k = args.pad_scale
    k_max = float(np.sqrt(36_000_000 * 0.96 / (ow * oh)))  # 接口 36MP 上限
    best = None
    for attempt in range(1, args.max_tries + 1):
        prompt = build_prompt(cfg, args.mode, extra)
        k_use = min(k, k_max)
        canvas = padded_canvas(orig, k_use)
        print(f"[try {attempt}] 生成中…（白边补偿 k={k_use:.2f}）", flush=True)
        url = gen.text2image(prompt, args.size, canvas)
        cand = load_rgb_from_url(url)
        score, err = framing_error(engine, orig, cand, orig_eyes)
        print(f"[try {attempt}] 构图偏差={score:.3f} (scale={err['scale']:.3f}, "
              f"dx={err['dx']:+.3f}, dy={err['dy']:+.3f})", flush=True)
        if best is None or score < best[0]:
            best = (score, cand, err)
        if score <= args.tolerance:
            break
        # 脸偏大就加大白边（封顶受像素上限约束）；结果有随机性，交替加点抖动
        jitter = 1.0 if attempt % 2 else 0.9
        k = float(np.clip(k * max(err["scale"], 0.7) * jitter, 2.4, k_max))
        extra = ["参考图人物四周保留有大面积纯色背景留白，成图取景必须与参考图的留白比例一致，"
                 "不要把人物放大填满画面、不要推近裁切。"] + correction_hints(err, cfg)
        time.sleep(1)

    score, cand, err = best
    stem, mode_name = args.image.stem, cfg["modes"][args.mode]["name"]
    pure = score <= args.tolerance
    method = "整图生成对齐" if pure else "局部合成兜底"

    if pure:
        native = align_warp(engine, orig, cand, orig_eyes, (ow, oh))[0]
    else:
        native = composite(engine, orig, cand, (ow, oh))
    native_path = out_dir / f"{stem}_{mode_name}_原尺寸.jpg"
    Image.fromarray(native).save(native_path, quality=95, dpi=(300, 300))

    hd_h = {"2K": 2464, "3K": 3520, "4K": 4704}[args.size]
    hd_w = round(hd_h * ow / oh)
    if pure:
        hd = align_warp(engine, orig, cand, orig_eyes, (hd_w, hd_h))[0]
    else:
        hd = composite(engine, orig, cand, (hd_w, hd_h))
    hd_path = out_dir / f"{stem}_{mode_name}_{args.size}.jpg"
    Image.fromarray(hd).save(hd_path, quality=95, dpi=(300, 300))

    cmp_path = out_dir / f"_对比_{stem}_{mode_name}.jpg"
    compare_sheet(orig, hd, cmp_path)

    print(json.dumps({
        "framing_error": round(score, 4),
        "method": method,
        "native": str(native_path), "hd": str(hd_path), "compare": str(cmp_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
