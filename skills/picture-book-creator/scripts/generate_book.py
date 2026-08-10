#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道德经绘本插图批量生成脚本"""
import os
import sys
import time


def load_env(path):
    """手动解析.env文件，避免依赖python-dotenv"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


load_env("/home/chenxiang.101/agents/skills/image-generator/.env")  # fallback到全局配置
load_env(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "../../../.env"))  # 优先读项目根目录.env
from openai import OpenAI
import requests

client = OpenAI(
    base_url=os.getenv("IMAGE_GEN_BASE_URL"),
    api_key=os.getenv("IMAGE_GEN_API_KEY"),
    timeout=300,
)
MODEL = os.getenv("IMAGE_GEN_MODEL")
OUT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/images"
os.makedirs(OUT_DIR, exist_ok=True)

STYLE_PREFIX = (
    "中国传统水墨画风格绘本插图，宣纸质感，淡墨渲染与留白结合，"
    "古典东方美学，意境空灵悠远，无文字，无水印。"
)

TASKS = [
    (
        "cover.jpg",
        "绘本封面。辽阔远山层叠隐于云海，一轮圆月悬于天际，"
        "山脚一叶扁舟漂于静水之上，大面积留白，气象苍茫，"
        "画面正中上方留出放置书名的空白区域，构图大气恢弘。",
    ),
    (
        "chapter1.jpg",
        "第一章『体道』意境：云雾缭绕的深邃山谷，一扇若隐若现的石门半开于烟岚之中，"
        "门内幽深莫测，门外溪流蜿蜒，表现玄之又玄众妙之门的神秘感。",
    ),
    (
        "chapter2.jpg",
        "第二章『养身』意境：山水相依，一轮太极阴阳隐现于圆月与倒影之间，"
        "高处山峰与低处水面相互映照，黑白浓淡对比，表现有无相生难易相成的辩证之美。",
    ),
    (
        "chapter3.jpg",
        "第三章『安民』意境：宁静的田园村落，农人荷锄归家，炊烟袅袅升起，"
        "远山如黛，田畴平整，一派安详无为而治的太平景象。",
    ),
    (
        "chapter4.jpg",
        "第四章『无源』意境：深不见底的幽潭峡谷，水面平静如镜却暗流涌动，"
        "四周峭壁环抱，烟岚升腾，表现道冲而用之或不盈的渊深莫测。",
    ),
    (
        "chapter5.jpg",
        "第五章『虚用』意境：天地之间一片苍茫，风吹芦苇起伏如浪，"
        "虚空中若有一只巨大的风箱橐籥意象，表现虚而不屈动而愈出的生生不息。",
    ),
]


def generate(filename, prompt, size="2k", retries=3):
    out_path = os.path.join(OUT_DIR, filename)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
        print("skip (exists): {}".format(filename))
        return True

    full_prompt = STYLE_PREFIX + prompt
    for attempt in range(1, retries + 1):
        try:
            print("generating {} (attempt {}/{})...".format(filename, attempt, retries))
            r = client.images.generate(
                model=MODEL,
                prompt=full_prompt,
                size=size,
                response_format="url",
                extra_body={"watermark": False},
            )
            url = r.data[0].url
            img_data = requests.get(url, timeout=120).content
            with open(out_path, "wb") as f:
                f.write(img_data)
            print("  saved: {} ({} KB)".format(out_path, len(img_data) // 1024))
            return True
        except Exception as e:
            msg = str(e)
            print("  error: {}".format(msg[:300]))
            # 尺寸不支持时回退到2K
            if "size" in msg.lower() and size != "2K":
                print("  fallback to size=2K")
                size = "2K"
            time.sleep(3 * attempt)
    return False


def main():
    ok = 0
    for filename, prompt in TASKS:
        if generate(filename, prompt):
            ok += 1
    print("\nResult: {}/{} images generated".format(ok, len(TASKS)))
    if ok < len(TASKS):
        sys.exit(1)


if __name__ == "__main__":
    main()
