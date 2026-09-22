#!/usr/bin/env python3
"""基于海报批量生成竖屏趣味短视频。

两个子命令：
  make   每组海报按轮转风格窗口批量生成 N 个视频（跨组覆盖全部风格）
  fill   不足 N 个的组，按优先级逐个补风格，内容审核拦截立即换下一个

特性：
  - 海报目录、视频输出、数量、画幅、时长、清晰度、并发全部命令行参数化
  - 动作库内置 30 种风格，可用 --motion-file 新增/覆盖
  - 断点续跑：已存在且大于 100KB 的视频自动跳过
  - --dry-run 只打印计划，不调用接口

用法示例见 skills/video-generator/SKILL.md。
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
from volcenginesdkarkruntime import Ark
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

BUILTIN_MOTION: dict[str, str] = {
    "pixar3d": "角色开心地朝镜头奔跑挥手，露出灿烂大笑，镜头轻微推进，阳光海岛氛围",
    "ghibli": "微风拂动头发与衣角，角色回眸温柔一笑，天上大朵白云流动，镜头缓慢横移",
    "cyberpunk": "霓虹雨夜中角色戴上兜帽转身，身上全息光环旋转亮起，镜头环绕推进",
    "vaporwave": "角色随复古电子节奏轻轻摇摆身体，粉紫落日与棕榈树在身后缓缓后退",
    "superhero": "英雄迎风腾空起飞，披风猛烈飘动，城市在脚下飞速掠过，仰拍跟随",
    "shonen": "角色热血跃起挥拳，周围速度线与气浪爆发，镜头快速拉远再猛推近",
    "popart": "撞色背景上大波点随节奏跳动，角色俏皮地连续变换拍照姿势，漫画式快切",
    "vintagetravel": "老胶片质感，角色优雅转身向镜头挥手致意，棕榈树随风摇曳",
    "space": "宇航员在空间站舷窗边缓缓转身，蓝色地球在身后转动，小物件失重飘浮",
    "wuxia": "侠客拔剑旋身腾空而起，衣袂与长发翻飞，四周水墨山水晕染流动",
    "gothic": "黑袍法师缓缓抬头，法杖顶端魔法光球亮起，蝙蝠成群掠过，镜头环绕",
    "pixel": "像素小人在复古游戏场景里蹦跳前进，头顶弹出金币，8-bit 质感",
    "lego": "乐高人偶一蹦一跳地挥手，周围彩色积木块凭空拼搭升起，镜头环绕",
    "papercut": "多层剪纸场景像舞台一样层层展开，纸雕小人在纸面上走动，纸张轻轻摆动",
    "ukiyoe": "浮世绘大海浪翻涌飞溅，和服人物转身挥动衣袖，画面保留纸纹笔触",
    "newyear": "年画人物笑容满面拱手拜年，红灯笼轻晃，夜空中烟花次第绽放",
    "swiss": "极简几何色块在画面中滑动重组，人物从色块后走入画面居中站定",
    "disco": "闪光球旋转洒下光点，角色跳起复古迪斯科舞步，舞厅霓虹随节拍闪烁",
    "clay": "黏土小人憨憨地蹦跳挥手，黏土布景随动作出现可爱的轻微形变",
    "picturebook": "绘本翻页进入魔法森林，小精灵提着灯笼飞舞，角色笑着去追萤火虫",
    "noir": "黑白高对比光影中角色缓步回眸，雨丝斜落，烟雾缭绕，老电影质感",
    "graffiti": "涂鸦墙前角色一个利落街舞定格，转身用喷漆喷出彩色新图案，镜头跟随",
    "baroque": "宫廷礼服人物优雅行礼后缓缓转身，烛火摇曳映亮金饰，镜头缓推",
    "chibi": "Q版大头角色蹦蹦跳跳卖萌转圈，周围弹出爱心和星星，笑容元气满满",
    "steampunk": "黄铜齿轮转动、蒸汽喷出，飞艇隆隆掠过头顶，角色扶帽抬头仰望",
    "underwater": "潜水角色呼出串串气泡，彩色鱼群环绕游过，阳光成束穿透海面",
    "candy": "角色在糖果世界开心地转圈起舞，巨大棒棒糖和马卡龙在周围弹跳",
    "rpg": "游戏卡带中的角色拔剑摆出战斗起手式，头顶弹出血条与技能光效",
    "disney": "梦幻城堡前烟花绽放，角色张开手臂开心转圈挥手，金色光斑飘散",
    "glitch": "画面出现故障闪烁与色彩错位，角色瞬间移动到镜头前酷炫定格，数字噪点飞散",
}

DEFAULT_PRIORITY = [
    "chibi", "clay", "lego", "pixel", "picturebook", "papercut",
    "newyear", "pixar3d", "ghibli", "popart", "shonen", "ukiyoe",
    "rpg", "swiss", "vintagetravel", "wuxia", "candy", "disney",
    "glitch", "vaporwave", "baroque", "disco", "steampunk",
    "underwater", "graffiti", "noir", "gothic", "space",
    "cyberpunk", "superhero",
]

DEFAULT_PROMPT_TEMPLATE = (
    "以参考图中的人物五官、服装、人物关系和整体画风为准，全程保持与参考图完全一致。"
    "竖屏趣味短视频：{motion}。"
    "运镜流畅有电影感，动作自然连贯，画面生动有趣，"
    "自动配上与画面风格贴合的音效和背景音乐。"
)

MIN_OK_BYTES = 100 * 1024
_tls = threading.local()


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_motion_catalog(motion_file: Path | None) -> dict[str, str]:
    catalog = dict(BUILTIN_MOTION)
    if motion_file:
        catalog.update(json.loads(motion_file.read_text(encoding="utf-8")))
    return catalog


def list_groups(posters_dir: Path, skip_dirs: set[str]) -> list[str]:
    return sorted(p.name for p in posters_dir.iterdir()
                  if p.is_dir() and p.name not in skip_dirs and not p.name.startswith("."))


def find_poster(group_dir: Path, slug: str) -> Path | None:
    matches = sorted(group_dir.glob(f"*_{slug}.*"))
    return matches[0] if matches else None


def existing_slugs(out_dir: Path, group: str) -> set[str]:
    group_dir = out_dir / group
    if not group_dir.exists():
        return set()
    return {f.stem.split("_", 1)[1] for f in group_dir.glob("*.mp4")
            if f.stat().st_size > MIN_OK_BYTES and "_" in f.stem}


def make_client() -> Ark:
    current = getattr(_tls, "client", None)
    if current is None:
        current = Ark(base_url=os.getenv("VIDEO_GEN_BASE_URL"),
                      api_key=os.getenv("VIDEO_GEN_API_KEY"), timeout=120.0)
        _tls.client = current
    return current


def image_to_data_url(path: Path) -> str:
    image = Image.open(path).convert("RGB")
    image.thumbnail((1536, 1536))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build_prompt(slug: str, motion_catalog: dict[str, str], template: str) -> str:
    return template.format(motion=motion_catalog[slug])


def submit_and_wait(task: dict, common: argparse.Namespace) -> dict:
    """提交任务并轮询，成功落盘。内容审核类失败标记为 blocked。"""
    out = Path(task["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        create = make_client().content_generation.tasks.create(
            model=os.getenv("VIDEO_GEN_MODEL"),
            content=[
                {"type": "text", "text": task["prompt"]},
                {"type": "image_url",
                 "image_url": {"url": image_to_data_url(Path(task["poster"]))},
                 "role": "reference_image"},
            ],
            generate_audio=True, ratio=common.ratio, duration=common.duration,
            resolution=common.resolution, watermark=False,
        )
        deadline = time.time() + common.timeout_s
        while time.time() < deadline:
            res = make_client().content_generation.tasks.get(task_id=create.id)
            if res.status == "succeeded":
                data = requests.get(res.content.video_url, timeout=180).content
                if len(data) < MIN_OK_BYTES:
                    return {"ok": False, "blocked": False, "error": "download too small"}
                out.write_bytes(data)
                return {"ok": True, "bytes": len(data),
                        "seconds": round(time.time() - (deadline - common.timeout_s))}
            if res.status == "failed":
                msg = str(res.error)
                blocked = any(k in msg for k in ("Sensitive", "copyright", "PolicyViolation"))
                return {"ok": False, "blocked": blocked, "error": msg}
            time.sleep(10)
        return {"ok": False, "blocked": False, "error": "poll timeout"}
    except Exception as exc:  # noqa: BLE001
        msg = repr(exc)
        return {"ok": False, "blocked": "400" in msg or "Sensitive" in msg, "error": msg}


def build_make_tasks(common: argparse.Namespace, motion_catalog: dict[str, str],
                     template: str) -> list[dict]:
    slugs = list(motion_catalog)
    groups = list_groups(common.posters_dir, common.skip_dirs)
    tasks = []
    for gi, group in enumerate(groups):
        for k in range(common.videos_per_group):
            slug = slugs[(gi * common.videos_per_group + k) % len(slugs)]
            poster = find_poster(common.posters_dir / group, slug)
            out = common.out_dir / group / f"{k + 1:02d}_{slug}.mp4"
            if poster is None:
                continue
            if out.exists() and out.stat().st_size > MIN_OK_BYTES:
                continue
            tasks.append({"group": group, "slug": slug, "poster": str(poster),
                          "out": str(out),
                          "prompt": build_prompt(slug, motion_catalog, template)})
    return tasks


def run_make(common: argparse.Namespace) -> int:
    template = common.prompt_template
    catalog = load_motion_catalog(common.motion_file)
    tasks = build_make_tasks(common, catalog, template)
    groups = list_groups(common.posters_dir, common.skip_dirs)
    log(f"groups={len(groups)} pending={len(tasks)} ratio={common.ratio} "
        f"duration={common.duration}s res={common.resolution} workers={common.workers}")
    if common.dry_run:
        for task in tasks:
            log(f"plan {task['group']}/{task['slug']} -> {task['out']}")
        return 0

    common.out_dir.mkdir(parents=True, exist_ok=True)
    done = ok_count = fail_count = 0
    failures = []
    with ThreadPoolExecutor(max_workers=common.workers) as pool:
        futures = [pool.submit(submit_and_wait, task, common) for task in tasks]
        for future in as_completed(futures):
            task = tasks[done]
            result = future.result()
            done += 1
            if result["ok"]:
                ok_count += 1
                log(f"[{done}/{len(tasks)}] OK {task['group']}/{task['slug']} "
                    f"{result['seconds']}s {result['bytes'] // 1024}KB")
            else:
                fail_count += 1
                failures.append({"group": task["group"], "slug": task["slug"],
                                 "error": result["error"]})
                log(f"[{done}/{len(tasks)}] FAIL {task['group']}/{task['slug']} {result['error'][:160]}")
    if failures:
        (common.out_dir / "failures.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"DONE ok={ok_count} fail={fail_count} out={common.out_dir}")
    return 0 if not fail_count else 1


def fill_one_group(group: str, common: argparse.Namespace, catalog: dict[str, str],
                   template: str, priority: list[str]) -> dict:
    have = existing_slugs(common.out_dir, group)
    seq = common.target + 1
    tried: set[str] = set()
    added = 0
    notes = []
    while len(have) + added < common.target:
        candidate = next((s for s in priority
                          if s not in have and s not in tried
                          and find_poster(common.posters_dir / group, s) is not None), None)
        if candidate is None:
            break
        tried.add(candidate)
        poster = find_poster(common.posters_dir / group, candidate)
        task = {"group": group, "slug": candidate, "poster": str(poster),
                "out": str(common.out_dir / group / f"{seq:02d}_{candidate}.mp4"),
                "prompt": build_prompt(candidate, catalog, template)}
        seq += 1
        result = submit_and_wait(task, common)
        if result["ok"]:
            added += 1
            log(f"FILL OK {group}/{candidate} {result['bytes'] // 1024}KB")
        else:
            notes.append(f"{candidate}: {result['error'][:150]}")
            log(f"FILL skip {group}/{candidate}: {result['error'][:150]}")
            if not result["blocked"]:
                time.sleep(8)
    return {"group": group, "added": added,
            "total": len(existing_slugs(common.out_dir, group)), "notes": notes}


def run_fill(common: argparse.Namespace) -> int:
    template = common.prompt_template
    catalog = load_motion_catalog(common.motion_file)
    if common.priority_file:
        priority = json.loads(common.priority_file.read_text(encoding="utf-8"))
    else:
        priority = [s for s in DEFAULT_PRIORITY if s in catalog]
    groups = list_groups(common.posters_dir, common.skip_dirs)
    needing = [g for g in groups if len(existing_slugs(common.out_dir, g)) < common.target]
    log(f"groups needing fill: {needing}")
    if common.dry_run:
        for group in needing:
            log(f"plan fill {group}, priority: {priority}")
        return 0

    common.out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=common.workers) as pool:
        futures = [pool.submit(fill_one_group, g, common, catalog, template, priority)
                   for g in needing]
        for future in as_completed(futures):
            result = future.result()
            log(f"== {result['group']} added={result['added']} total={result['total']}")
    log(f"FINAL {{{', '.join(g + ': ' + str(len(existing_slugs(common.out_dir, g))) for g in groups)}}}")
    return 0


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--posters-dir", required=True, type=Path, help="海报目录，每组一个子目录")
    parser.add_argument("--out-dir", required=True, type=Path, help="视频输出目录")
    parser.add_argument("--motion-file", type=Path, default=None,
                        help="JSON 文件，新增/覆盖动作描述：{slug: 动作文本}")
    parser.add_argument("--prompt-template", default=DEFAULT_PROMPT_TEMPLATE,
                        help="提示词模板，占位符 {motion}")
    parser.add_argument("--ratio", default="9:16")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-s", type=int, default=20 * 60, help="单个任务轮询上限秒数")
    parser.add_argument("--skip-dirs", default="_converted,_resized,_sheets,_gallery,_cache",
                        help="海报目录下要忽略的子目录，逗号分隔")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不调用接口")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="海报批量生成视频：make / fill")
    common_parent = argparse.ArgumentParser(add_help=False)
    add_common_args(common_parent)
    sub = parser.add_subparsers(dest="command", required=True)

    make_parser = sub.add_parser("make", parents=[common_parent], help="每组批量生成 N 个视频")
    make_parser.add_argument("--videos-per-group", type=int, default=5)

    fill_parser = sub.add_parser("fill", parents=[common_parent], help="按优先级为不足 N 个视频的组补齐")
    fill_parser.add_argument("--target", type=int, default=5)
    fill_parser.add_argument("--priority-file", type=Path, default=None,
                             help="JSON 数组，风格 slug 的补齐优先级")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.skip_dirs = {s.strip() for s in args.skip_dirs.split(",") if s.strip()}
    if args.command == "make":
        args.videos_per_group = args.videos_per_group
        return run_make(args)
    return run_fill(args)


if __name__ == "__main__":
    raise SystemExit(main())
