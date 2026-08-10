#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""picture-book skill · seedream 批量出图脚本（含重试/断点续跑/超时保护）

用法:
  python batch_generate.py <prompts.json> --out <dir> [--size 2K] [--project <root>]

prompts.json 格式:
  [{"name": "01-cover", "prompt": "..."}, {"name": "x", "prompt": "...", "image": "/path/ref.jpg"}]
  - image 字段可选：提供时走图生图（风格转换），否则纯文生图。

依赖项目 .env 中的 IMAGE_GEN_BASE_URL / IMAGE_GEN_API_KEY / IMAGE_GEN_MODEL。
ImageGenerator 类已随本脚本同目录的 generator.py 自带（自包含，不依赖项目内 image-generator skill）。
"""
import argparse
import json
import os
import sys
import time

# 已存在文件视为完成的最小字节数（小于此值认为是损坏/截断图，会重新生成）
MIN_VALID_SIZE = 10_000


def _find_project_root(start_dir):
    """从 start_dir 向上查找含 .env 的目录作为项目根，找不到则返回 start_dir。"""
    d = os.path.abspath(start_dir)
    while True:
        if os.path.exists(os.path.join(d, ".env")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start_dir)
        d = parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompts_json")
    ap.add_argument("--out", required=True, help="图片输出目录")
    ap.add_argument("--size", default="2K", choices=["2K", "3K", "4K"])
    ap.add_argument("--project", default=None,
                    help="项目根目录（含 .env）。默认从当前目录向上查找 .env")
    args = ap.parse_args()

    root = args.project or _find_project_root(os.getcwd())
    # 自包含版本：优先从本脚本同目录找 generator.py，找不到再回退项目内 image-generator
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(os.path.join(root, "skills/image-generator/scripts"))
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv:
        load_dotenv(os.path.join(root, ".env"))
    else:  # 兜底：手工解析 .env
        env_file = os.path.join(root, ".env")
        if os.path.exists(env_file):
            with open(env_file) as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())

    # 早校验必需的环境变量，缺失时立即报错退出（勿盲试无效 key）
    missing = [k for k in ("IMAGE_GEN_BASE_URL", "IMAGE_GEN_API_KEY", "IMAGE_GEN_MODEL")
               if not os.getenv(k)]
    if missing:
        print(f"ERROR: 缺少必需的环境变量: {missing}，请检查 {root}/.env", flush=True)
        sys.exit(2)

    from generator import ImageGenerator
    from openai import OpenAI
    import requests

    os.makedirs(args.out, exist_ok=True)
    with open(args.prompts_json, encoding="utf-8") as fh:
        tasks = json.load(fh)
    # 校验任务格式，缺失字段时给出清晰报错而非 KeyError
    for idx, t in enumerate(tasks):
        if not isinstance(t, dict) or not t.get("name") or not t.get("prompt"):
            print(f"ERROR: prompts.json 第 {idx} 条缺少 name 或 prompt 字段: {t}", flush=True)
            sys.exit(2)
    print(f"共 {len(tasks)} 张图待处理，输出目录: {args.out}", flush=True)

    gen = ImageGenerator(
        base_url=os.getenv("IMAGE_GEN_BASE_URL"),
        api_key=os.getenv("IMAGE_GEN_API_KEY"),
        model_name=os.getenv("IMAGE_GEN_MODEL"),
    )
    # 关键：覆盖默认 600s 超时，防止单张卡死整个批次
    gen.client = OpenAI(
        base_url=os.getenv("IMAGE_GEN_BASE_URL"),
        api_key=os.getenv("IMAGE_GEN_API_KEY"),
        timeout=120.0,
    )

    ok, failed = [], []
    for i, t in enumerate(tasks):
        name = t["name"]
        ext = ".jpg"
        out = os.path.join(args.out, name + ext)
        if os.path.exists(out) and os.path.getsize(out) > MIN_VALID_SIZE:
            print(f"[{i:02d}] SKIP (exists): {name}", flush=True)
            ok.append(name)
            continue
        done = False
        for attempt in range(1, 4):
            try:
                t0 = time.time()
                url = gen.text2image(t["prompt"], size=args.size,
                                     source_image=t.get("image"))
                img = requests.get(url, timeout=120)
                img.raise_for_status()
                with open(out, "wb") as f:
                    f.write(img.content)
                print(f"[{i:02d}] OK {name}  {len(img.content)//1024}KB  "
                      f"{time.time()-t0:.0f}s", flush=True)
                ok.append(name)
                done = True
                break
            except Exception as e:
                print(f"[{i:02d}] attempt {attempt} failed: {e}", flush=True)
                time.sleep(5 * attempt)
        if not done:
            failed.append(name)

    print(f"\nDONE. ok={len(ok)} failed={len(failed)}", flush=True)
    if failed:
        print("FAILED:", failed, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
