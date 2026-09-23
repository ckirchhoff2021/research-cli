#!/usr/bin/env python3
"""Browser-free SVG geometry check for architecture-diagram HTML output.

Usage:
    python3 svg_geom_check.py <diagram.html> [containers.json]

No browser, no vision needed. Checks:
  1. rect/text out of viewBox bounds
  2. text soft-overflow: centered text wider than its container box
     (CJK-aware width estimation; ASCII ~= 0.62em for JetBrains Mono)

containers.json is optional; shape: {"name": [x, y, w, h], ...}
Exits 0 on pass, 1 on problems.
"""
import sys, json, re, unicodedata
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"


def is_cjk(ch):
    return unicodedata.east_asian_width(ch) in ("W", "F")


def text_width(s, fs):
    w = 0.0
    for ch in s:
        w += fs if is_cjk(ch) else 0.62 * fs
    return w


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    html = open(sys.argv[1], encoding="utf-8").read()
    m = re.search(r"<svg.*?</svg>", html, re.S)
    if not m:
        print("no <svg> found")
        sys.exit(1)
    # <svg> already carries xmlns; do NOT re-inject (duplicate-attribute error)
    root = ET.fromstring(m.group(0))

    vb = list(map(float, root.attrib.get("viewBox", "0 0 1200 760").split()))
    VW, VH = vb[2], vb[3]
    print(f"viewBox: {vb[0]} {vb[1]} {VW} {VH}")

    containers = {}
    if len(sys.argv) >= 3:
        containers = json.load(open(sys.argv[2], encoding="utf-8"))

    problems = []
    for el in root.iter():
        tag = el.tag.replace(NS, "")
        if tag == "rect":
            x = float(el.attrib.get("x", 0)); y = float(el.attrib.get("y", 0))
            w = float(el.attrib.get("width", 0)); h = float(el.attrib.get("height", 0))
            if x < 0 or y < 0 or x + w > VW or y + h > VH:
                problems.append(f"rect out of bounds: x={x} y={y} w={w} h={h}")
        elif tag == "text":
            x = float(el.attrib.get("x", 0)); y = float(el.attrib.get("y", 0))
            fs = float(el.attrib.get("font-size", 10))
            anchor = el.attrib.get("text-anchor", "start")
            s = "".join(el.itertext()).strip()
            tw = text_width(s, fs)
            left = x - tw / 2 if anchor == "middle" else x
            right = x + tw / 2 if anchor == "middle" else x + tw
            if left < 0 or right > VW or y > VH:
                problems.append(f"text out of bounds: '{s[:20]}' x={x} anchor={anchor} w~={tw:.0f} y={y}")
            if anchor == "middle":
                for name, (cx, cy, cw, ch) in containers.items():
                    if cx <= x <= cx + cw and cy <= y <= cy + ch and tw > cw:
                        problems.append(f"text overflows [{name}]: '{s[:30]}' w~={tw:.0f} > {cw}")

    if problems:
        print(f"\n!! {len(problems)} problem(s):")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("\nOK: no out-of-bounds or soft-overflow issues")


if __name__ == "__main__":
    main()
