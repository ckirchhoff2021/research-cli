#!/usr/bin/env python3
"""批量风格迁移：对参考图目录中的每张图，按选定风格批量生成趣味海报。

特性：
  - 参考目录、输出目录、风格集合、尺寸、并发数全部通过命令行参数指定
  - 断点续跑：已存在且大于 20KB 的结果自动跳过
  - 风格目录内置 30 种，可用 --styles 挑选子集，--styles-file 新增/覆盖
  - --dry-run 只打印执行计划，不调用任何接口

用法示例见 skills/image-generator/SKILL.md。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

# 内置风格目录：slug -> (风格名, 画面变换描述)
BUILTIN_STYLES: dict[str, dict[str, str]] = {
    "pixar3d": {"name": "皮克斯3D动画", "transform": "人物变为可爱的3D卡通形象，身处阳光明媚的热带海岛，皮克斯电影质感"},
    "ghibli": {"name": "吉卜力手绘", "transform": "手绘动画质感，温暖治愈的海边小镇与蓝天白云，吉卜力工作室风格"},
    "cyberpunk": {"name": "赛博朋克", "transform": "霓虹闪烁的雨夜未来都市，机能风服装与全息光效"},
    "vaporwave": {"name": "蒸汽波复古", "transform": "粉紫渐变配色、复古电子元素、棕榈树与落日，Vaporwave风格"},
    "superhero": {"name": "超级英雄漫画", "transform": "美式漫画超级英雄封面，披风战衣，强烈动感构图"},
    "shonen": {"name": "日漫热血", "transform": "日式少年热血漫画封面，夸张帅气动作、速度线与明快网点"},
    "popart": {"name": "波普艺术", "transform": "高饱和撞色、网点印刷，安迪·沃霍尔式波普艺术"},
    "vintagetravel": {"name": "复古旅行海报", "transform": "上世纪中期度假宣传画风格，复古插画质感"},
    "space": {"name": "太空科幻大片", "transform": "身穿宇航服、星际飞船与蓝色地球，IMAX科幻电影质感"},
    "wuxia": {"name": "武侠水墨", "transform": "古装侠客造型，山水水墨与江湖意境，武侠电影海报"},
    "gothic": {"name": "哥特暗黑奇幻", "transform": "暗黑魔法城堡、魔幻装束、神秘冷峻光影，奇幻电影海报"},
    "pixel": {"name": "像素游戏封面", "transform": "8-bit复古像素艺术，怀旧电子游戏封面风格"},
    "lego": {"name": "乐高积木世界", "transform": "人物变身为乐高人偶，置身积木搭建的欢乐世界"},
    "papercut": {"name": "剪纸纸雕", "transform": "多层纸雕与剪纸拼贴艺术，层次分明、色彩明快"},
    "ukiyoe": {"name": "日式浮世绘", "transform": "日本浮世绘风格，海浪、和服与和风线条"},
    "newyear": {"name": "中国年画工笔", "transform": "中国年画与工笔重彩，喜庆热烈、装饰性强"},
    "swiss": {"name": "极简北欧设计", "transform": "极简几何构成与国际主义排版，干净高级"},
    "disco": {"name": "80年代迪斯科", "transform": "迪斯科舞厅、闪光球、复古装束与霓虹"},
    "clay": {"name": "黏土定格动画", "transform": "黏土定格动画质感，造型憨厚可爱，布景温暖"},
    "picturebook": {"name": "童话绘本封面", "transform": "柔和梦幻的童话绘本封面，魔法森林般的氛围"},
    "noir": {"name": "黑白黑色电影", "transform": "黑白胶片侦探电影质感，高对比光影与复古氛围"},
    "graffiti": {"name": "街头涂鸦潮流", "transform": "嘻哈街头涂鸦与喷漆艺术，潮流前卫、色彩大胆"},
    "baroque": {"name": "巴洛克宫廷油画", "transform": "巴洛克/文艺复兴宫廷油画，华丽礼服与伦勃朗光"},
    "chibi": {"name": "Q版卖萌", "transform": "大头Q版卡通形象，俏皮卖萌，糖果色调"},
    "steampunk": {"name": "蒸汽朋克", "transform": "维多利亚时代齿轮、黄铜机械与复古飞艇"},
    "underwater": {"name": "深海奇遇", "transform": "潜水装束与奇幻海底世界，珊瑚、鱼群与气泡"},
    "candy": {"name": "糖果泡泡世界", "transform": "梦幻糖果与甜点世界，马卡龙色彩、漂浮泡泡"},
    "rpg": {"name": "复古RPG游戏", "transform": "复古奇幻角色扮演游戏卡带封面，勇者冒险氛围"},
    "disney": {"name": "迪士尼歌舞动画", "transform": "经典歌舞动画风，华丽舞台、城堡与烟花"},
    "glitch": {"name": "数字故障艺术", "transform": "RGB色彩错位、数字故障与像素撕裂的未来感海报"},
}

DEFAULT_PROMPT_TEMPLATE = (
    "将参考照片创作成一张「{style_name}」风格的趣味海报。"
    "严格保留照片中人物的面部特征、长相、人数、年龄、性别和亲密关系，主角就是照片里的人；"
    "{transform}。海报级构图，竖版排版，富有戏剧性与故事感，细节丰富，画质精美，整体氛围欢乐有趣。"
)

_print_lock = threading.Lock()


def log(message: str) -> None:
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def collect_refs(refs_dir: Path, extensions: set[str], recursive: bool) -> list[tuple[str, Path]]:
    iterator = refs_dir.rglob("*") if recursive else refs_dir.glob("*")
    refs = [(p.stem, p) for p in sorted(iterator)
            if p.is_file() and p.suffix.lower().lstrip(".") in extensions]
    return refs


def load_style_catalog(styles_file: Path | None) -> dict[str, dict[str, str]]:
    catalog = {slug: dict(meta) for slug, meta in BUILTIN_STYLES.items()}
    if styles_file:
        extra = json.loads(styles_file.read_text(encoding="utf-8"))
        for slug, meta in extra.items():
            catalog[slug] = {"name": meta.get("name", slug),
                             "transform": meta.get("transform", "")}
    return catalog


def resolve_styles(catalog: dict[str, dict[str, str]], selected: str | None) -> list[str]:
    slugs = list(catalog) if not selected else [s.strip() for s in selected.split(",") if s.strip()]
    unknown = [s for s in slugs if s not in catalog]
    if unknown:
        raise SystemExit(f"unknown style slugs: {unknown} (known: {list(catalog)})")
    return slugs


def resize_payload(path: Path, long_edge: int) -> str:
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if long_edge > 0:
        image.thumbnail((long_edge, long_edge))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    encoded = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"


class PosterBatch:
    def __init__(self, size: str) -> None:
        self.client = OpenAI(base_url=os.getenv("IMAGE_GEN_BASE_URL"),
                             api_key=os.getenv("IMAGE_GEN_API_KEY"), timeout=120.0)
        self.model = os.getenv("IMAGE_GEN_MODEL")
        self.size = size

    def generate_one(self, ref_name: str, payload: str, index: int,
                     slug: str, style: dict[str, str], out_dir: Path,
                     prompt_template: str) -> Path:
        target = out_dir / ref_name / f"{index:02d}_{slug}.jpg"
        if target.exists() and target.stat().st_size > 20 * 1024:
            return target
        prompt = prompt_template.format(style_name=style["name"], transform=style["transform"])
        last_error = ""
        for attempt in range(4):
            try:
                response = self.client.images.generate(
                    model=self.model, prompt=prompt, size=self.size,
                    response_format="url",
                    extra_body={"watermark": False, "image": payload},
                )
                data = requests.get(response.data[0].url, timeout=180).content
                if len(data) < 20 * 1024:
                    raise RuntimeError(f"downloaded image too small: {len(data)} bytes")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                return target
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:160]
                time.sleep(2 ** attempt * 3)
        raise RuntimeError(f"{ref_name} {slug} failed: {last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量风格迁移：参考图 × 风格集 → 海报")
    parser.add_argument("--refs-dir", required=True, type=Path, help="参考图目录")
    parser.add_argument("--out-dir", required=True, type=Path, help="海报输出目录")
    parser.add_argument("--styles", default=None,
                        help="逗号分隔的风格 slug 子集，默认使用全部风格")
    parser.add_argument("--styles-file", type=Path, default=None,
                        help="JSON 文件，新增/覆盖风格：{slug: {name, transform}}")
    parser.add_argument("--prompt-template", default=DEFAULT_PROMPT_TEMPLATE,
                        help="提示词模板，占位符 {style_name} 与 {transform}")
    parser.add_argument("--size", default="2K", help="生成尺寸，默认 2K")
    parser.add_argument("--long-edge", type=int, default=1536,
                        help="参考图长边缩放，0 表示不缩放，默认 1536")
    parser.add_argument("--ext", default="jpg,jpeg,png,webp", help="接受的扩展名，逗号分隔")
    parser.add_argument("--recursive", action="store_true", help="递归扫描参考目录")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-refs", type=int, default=0, help="只取前 N 张参考图，0 为全部")
    parser.add_argument("--test", action="store_true", help="只执行第一个任务")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不调用接口")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    extensions = {e.strip().lower().lstrip(".") for e in args.ext.split(",") if e.strip()}
    refs = collect_refs(args.refs_dir, extensions, args.recursive)
    if not refs:
        raise SystemExit(f"no reference images found in {args.refs_dir}")
    if args.limit_refs:
        refs = refs[: args.limit_refs]

    catalog = load_style_catalog(args.styles_file)
    slugs = resolve_styles(catalog, args.styles)
    if args.test:
        refs, slugs = refs[:1], slugs[:1]

    jobs = [(ref_name, ref_path, index, slug)
            for ref_name, ref_path in refs
            for index, slug in enumerate(slugs, start=1)]
    pending = [(name, idx, slug) for name, _, idx, slug in jobs
               if not (args.out_dir / name / f"{idx:02d}_{slug}.jpg").exists()]
    log(f"refs={len(refs)} styles={len(slugs)} total={len(jobs)} pending={len(pending)} out={args.out_dir}")

    if args.dry_run:
        for name, path in refs:
            log(f"ref {name}: {path}")
        log(f"style order: {slugs}")
        return 0

    batch = PosterBatch(args.size)
    payload_cache: dict[str, str] = {}
    done = 0
    failures: list[str] = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for ref_name, ref_path, index, slug in jobs:
            if ref_name not in payload_cache:
                payload_cache[ref_name] = resize_payload(ref_path, args.long_edge)
            futures[pool.submit(batch.generate_one, ref_name, payload_cache[ref_name],
                                index, slug, catalog[slug], args.out_dir,
                                args.prompt_template)] = (ref_name, index, slug)
        for future in as_completed(futures):
            ref_name, index, slug = futures[future]
            try:
                path = future.result()
                done += 1
                log(f"[{done}/{len(jobs)}] {ref_name} #{index:02d} {catalog[slug]['name']} -> {path.name}")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{ref_name} #{index} {slug}: {exc}")
                log(f"FAILED {ref_name} #{index} {slug}: {exc}")

    elapsed = time.time() - started
    log(f"finished in {elapsed/60:.1f} min, {done} ok, {len(failures)} failed")
    if failures:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "failures.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
