#!/usr/bin/env python3
"""drama-video-creator: 剧情短视频创作全流程 CLI。
用法:
  drama.py doctor
  drama.py new "创意" [--shots N] [--ratio 16:9] [--resolution 1080p] [--style gufeng]
  drama.py voices <project_id>
  drama.py gen <project_id>
  drama.py compose <project_id>
  drama.py run "创意" [选项]     # 一键全流程
  drama.py redo <project_id> <shot_index>
  drama.py list
  drama.py status <project_id>
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time, re, tempfile, shutil
from pathlib import Path
from dataclasses import asdict

# ── Paths ──
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SKILL_DIR.parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "drama_video"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_GEN_SCRIPT = PROJECT_ROOT / "skills" / "video-generator" / "scripts" / "generator.py"
IMAGE_GEN_SCRIPT = PROJECT_ROOT / "skills" / "image-generator" / "scripts" / "generator.py"
TTS_SCRIPT = PROJECT_ROOT / "skills" / "speech-generator" / "scripts" / "tts.py"
VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python"

sys.path.insert(0, str(SCRIPT_DIR))
from config import get_settings, find_ffmpeg, project_dir, ensure_dirs, load_env
from creative import generate_script, build_shot_prompts, render_script_md, pick_voice
from tts_gen import generate_all_voices
from video_gen import generate_all_segments
from compose import compose_final

# ── Project IO ──
def save_project(p):
    p["updated_at"] = time.time()
    d = project_dir(p["id"])
    (d / "project.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also write markdown
    if p.get("script"):
        (d / "script.md").write_text(render_script_md(p["script"]), encoding="utf-8")
        shots_md_lines = [f"# {p['script'].get('title','')} 分镜表", "",
                          f"> 风格锚点：{p['script'].get('style_anchor','')}",
                          f"> 镜头数：{len(p['shots'])}", ""]
        for i, s in enumerate(p.get("shots", [])):
            shots_md_lines += [
                f"## 镜头{i+1:02d} {s.get('title','')}",
                f"- 场景：{s.get('scene','')}",
                f"- 动作：{s.get('action','')}",
                f"- 情绪：{s.get('emotion','')}",
                f"- 状态：{s.get('status','pending')}",
                f"- 视频：{s.get('video_file','')}",
                "",
            ]
        (d / "shots.md").write_text("\n".join(shots_md_lines), encoding="utf-8")

def load_project(pid):
    p = project_dir(pid) / "project.json"
    if not p.exists():
        print(f"项目不存在: {pid}"); sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))

def new_pid(name=""):
    ts = time.strftime("%Y%m%d-%H%M%S")
    suffix = re.sub(r'[^\w]', '_', name)[:10] if name else ""
    return f"{ts}-{suffix}" if suffix else ts

# ── Commands ──
def cmd_doctor(args):
    settings = get_settings()
    print("=== 环境检查 ===")
    print(f"  Python: {sys.version.split()[0]}")
    ff = find_ffmpeg()
    print(f"  ffmpeg: {'✓ ' + ff if ff else '✗ 未找到（请安装imageio-ffmpeg）'}")
    print(f"  Ark API Key: {'✓ 已配置' if settings['ark_api_key'] else '✗ 未配置'}")
    print(f"  LLM Model: {settings['llm_model']}")
    print(f"  Video Model: {settings['video_model']}")
    for name, path in [("video-generator", VIDEO_GEN_SCRIPT),
                        ("image-generator", IMAGE_GEN_SCRIPT),
                        ("speech-generator", TTS_SCRIPT)]:
        print(f"  {name}: {'✓' if path.exists() else '✗ 未找到'} {path}")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  输出目录: {OUTPUTS_DIR}")

def cmd_new(args):
    settings = get_settings()
    pid = new_pid(args.name or args.concept[:8])
    base = ensure_dirs(pid)
    print(f"=== 新建项目: {pid} ===")
    print(f"  创意: {args.concept}")
    print(f"  分镜数: {args.shots}, 比例: {args.ratio}, 分辨率: {args.resolution}, 风格: {args.style}")

    # 1. Generate script via LLM
    print("\n[1] LLM 创作剧本...")
    script_data = generate_script(args.concept, args.shots, args.style, args.ratio, args.resolution, settings)
    print(f"  片名: {script_data.get('title','')}")
    print(f"  角色: {', '.join(c['name'] for c in script_data.get('characters',[]))}")
    print(f"  分镜: {len(script_data.get('shots',[]))}个")

    # 2. Build shot prompts
    shots = build_shot_prompts(script_data)
    for s in shots:
        s["status"] = "pending"
        s["video_file"] = ""
        s["voices"] = []  # will be filled by voices step
    script_data["shots"] = shots

    # 3. Generate character reference images (CG style to avoid privacy detection)
    print("\n[2] 生成角色参考图...")
    chars_dir = base / "characters"
    for c in script_data.get("characters", []):
        ref_path = chars_dir / f"ref_{c['name']}.jpg"
        if not ref_path.exists():
            style_hint = script_data.get("style_anchor", "国风3D CG动画风格")
            prompt = (f"{style_hint}。角色定妆照：{c.get('appearance','')}，"
                      f"{c.get('tag','')}。{c.get('role','')}角色设定图，"
                      f"半身像，清晰面部，高质量CG插画风格（非真人照片）")
            print(f"  生成 {c['name']} 参考图...", end=" ", flush=True)
            r = subprocess.run(
                [str(VENV_PY), str(IMAGE_GEN_SCRIPT), "--prompt", prompt, "--size", "2K"],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=120)
            # Find latest generated image
            img_out_dir = PROJECT_ROOT / "skills" / "image-generator" / "outputs"
            imgs = sorted(img_out_dir.glob("dream_*.jpg"), key=os.path.getctime)
            if imgs:
                import shutil
                shutil.copy(imgs[-1], ref_path)
                c["ref_image"] = str(ref_path)
                print(f"OK → {ref_path.name}")
            else:
                print("WARN: no image output")
                c["ref_image"] = ""
        else:
            c["ref_image"] = str(ref_path)
            print(f"  {c['name']} 参考图已存在")

    project = {
        "id": pid,
        "name": script_data.get("title", args.concept[:20]),
        "concept": args.concept,
        "ratio": args.ratio,
        "resolution": args.resolution,
        "num_shots": args.shots,
        "style": args.style,
        "script": script_data,
        "shots": shots,
        "final_video": "",
        "status": "scripted",
        "error": "",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    save_project(project)
    print(f"\n✅ 项目创建完成: {pid}")
    print(f"  工作目录: {base}")
    print(f"  下一步: python drama.py voices {pid}")

def cmd_voices(args):
    p = load_project(args.project_id)
    base = ensure_dirs(p["id"])
    print(f"=== 生成配音: {p['id']} ===")
    generate_all_voices(p, base, VENV_PY, TTS_SCRIPT, PROJECT_ROOT)
    p["status"] = "voiced"
    save_project(p)
    print("✅ 配音生成完成")

def cmd_gen(args):
    p = load_project(args.project_id)
    base = ensure_dirs(p["id"])
    settings = get_settings()
    print(f"=== 生成视频片段: {p['id']} ===")
    generate_all_segments(p, base, VENV_PY, VIDEO_GEN_SCRIPT, PROJECT_ROOT, args)
    p["status"] = "generating"
    save_project(p)

def cmd_compose(args):
    p = load_project(args.project_id)
    base = ensure_dirs(p["id"])
    ff = find_ffmpeg()
    print(f"=== 合成成片: {p['id']} ===")
    compose_final(p, base, VENV_PY, ff, PROJECT_ROOT)
    p["status"] = "assembled"
    save_project(p)

def cmd_run(args):
    """Full pipeline: new → voices → gen → compose"""
    # Run new first
    args_new = argparse.Namespace(
        concept=args.concept, name=getattr(args, 'name', ''),
        shots=args.shots, ratio=args.ratio, resolution=args.resolution, style=args.style)
    cmd_new(args_new)
    # Find latest project
    projs = sorted(OUTPUTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    pid = projs[0].name
    print(f"\n>>> 继续配音...")
    cmd_voices(argparse.Namespace(project_id=pid))
    print(f"\n>>> 继续视频生成...")
    cmd_gen(argparse.Namespace(project_id=pid))
    print(f"\n>>> 继续合成...")
    cmd_compose(argparse.Namespace(project_id=pid))

def cmd_list(args):
    print("=== 项目列表 ===")
    if not OUTPUTS_DIR.exists():
        print("  暂无项目"); return
    for d in sorted(OUTPUTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir() and (d / "project.json").exists():
            p = json.loads((d / "project.json").read_text(encoding="utf-8"))
            done = sum(1 for s in p.get("shots",[]) if s.get("video_file"))
            total = len(p.get("shots",[]))
            fin = "✓" if p.get("final_video") else " "
            print(f"  [{fin}] {p['id']}  {p.get('name','')[:30]:30s}  {done}/{total} shots  {p['status']}")

def cmd_status(args):
    p = load_project(args.project_id)
    print(f"=== 项目状态: {p['id']} ===")
    print(f"  标题: {p.get('script',{}).get('title','')}")
    print(f"  状态: {p['status']}")
    if p.get("error"): print(f"  错误: {p['error']}")
    for i, s in enumerate(p.get("shots", [])):
        vf = "✓" if s.get("video_file") else " "
        print(f"  [{vf}] 镜头{i+1:02d} {s.get('title','')[:25]}  {s.get('status','')}")
    if p.get("final_video"): print(f"  成片: {p['final_video']}")

def main():
    load_env()
    parser = argparse.ArgumentParser(description="drama-video-creator 剧情短视频创作")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="环境检查").set_defaults(func=cmd_doctor)

    p_new = sub.add_parser("new", help="新建项目+生成剧本")
    p_new.add_argument("concept", help="一句话创意描述")
    p_new.add_argument("--name", default="", help="项目名")
    p_new.add_argument("--shots", type=int, default=7, help="分镜数(默认7)")
    p_new.add_argument("--ratio", default="16:9", choices=["16:9","9:16","1:1","21:9"])
    p_new.add_argument("--resolution", default="1080p", choices=["480p","720p","1080p"])
    p_new.add_argument("--style", default="gufeng", help="风格倾向")
    p_new.set_defaults(func=cmd_new)

    p_voi = sub.add_parser("voices", help="生成对白配音")
    p_voi.add_argument("project_id")
    p_voi.set_defaults(func=cmd_voices)

    p_gen = sub.add_parser("gen", help="生成视频片段")
    p_gen.add_argument("project_id")
    p_gen.set_defaults(func=cmd_gen)

    p_comp = sub.add_parser("compose", help="合成成片")
    p_comp.add_argument("project_id")
    p_comp.set_defaults(func=cmd_compose)

    p_run = sub.add_parser("run", help="一键全流程")
    p_run.add_argument("concept", help="一句话创意描述")
    p_run.add_argument("--name", default="")
    p_run.add_argument("--shots", type=int, default=7)
    p_run.add_argument("--ratio", default="16:9")
    p_run.add_argument("--resolution", default="1080p")
    p_run.add_argument("--style", default="gufeng")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("list", help="列出项目").set_defaults(func=cmd_list)

    p_st = sub.add_parser("status", help="项目状态")
    p_st.add_argument("project_id")
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
