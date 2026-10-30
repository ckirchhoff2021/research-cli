#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把场景/故事预设 JSON 导出为可读剧本 Markdown。

用法：
  python preset_to_screenplay.py --preset adventure-story \
      --output outputs/任务/剧本.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PRESETS_DIR = Path(__file__).resolve().parents[1] / "presets"


def resolve(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.is_file():
        return p
    p = PRESETS_DIR / f"{name_or_path}.json"
    if p.is_file():
        return p
    raise SystemExit(f"preset not found: {name_or_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", required=True)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    data = json.loads(resolve(args.preset).read_text(encoding="utf-8"))
    items = data["items"]
    title = args.title or "故事剧本"

    lines = [f"# {title}", ""]
    if data.get("prompt_prefix"):
        lines += ["> 统一设定：", f"> {data['prompt_prefix']}", ""]
    lines += [f"共 {len(items)} 集。", ""]

    last_theme = None
    for i, it in enumerate(items, start=1):
        theme = it.get("theme", "")
        if theme and theme != last_theme:
            lines += ["", f"## {theme}", ""]
            last_theme = theme
        dur = it.get("duration", "")
        lines.append(f"### 第{i:02d}集 · {it.get('title', it['slug'])}（{dur}s）")
        lines.append("")
        lines.append(it.get("prompt", ""))
        lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved screenplay: {args.output} ({len(items)} scenes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
