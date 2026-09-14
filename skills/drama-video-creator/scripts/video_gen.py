"""视频片段生成：调用 video-generator。"""
from __future__ import annotations
import subprocess, os, glob, time, shutil
from pathlib import Path

def generate_all_segments(project, base, venv_py, gen_script, project_root, args):
    """Generate video for each shot."""
    segs_dir = base / "segments"
    segs_dir.mkdir(exist_ok=True)
    out_dir = project_root / "skills" / "video-generator" / "outputs"
    chars = {c["name"]: c for c in project.get("script", {}).get("characters", [])}

    for si, shot in enumerate(project.get("shots", [])):
        idx = si + 1
        fname = f"shot_{idx:02d}.mp4"
        dest = segs_dir / fname
        if dest.exists() and os.path.getsize(dest) > 500000:
            shot["video_file"] = str(dest)
            shot["status"] = "done"
            print(f"  [SKIP] 镜头{idx:02d} 已存在")
            continue

        prompt = shot.get("prompt", "")
        # Collect reference images for characters in this shot
        ref_imgs = []
        for cn in shot.get("characters", []):
            c = chars.get(cn, {})
            ri = c.get("ref_image", "")
            if ri and os.path.exists(ri):
                ref_imgs.append(ri)
        images_arg = ",".join(ref_imgs) if ref_imgs else ""

        print(f"\n{'='*50}")
        print(f"  镜头{idx:02d}: {shot.get('title','')}")
        print(f"  角色: {', '.join(shot.get('characters',[]))}")
        print(f"{'='*50}")

        cmd = [str(venv_py), str(gen_script),
               "--prompt", prompt,
               "--ratio", project["ratio"],
               "--duration", "10",
               "--resolution", project["resolution"]]
        if images_arg:
            cmd += ["--images", images_arg]

        t0 = time.time()
        for attempt in range(2):
            r = subprocess.run(cmd, capture_output=False, text=True,
                             cwd=str(project_root), timeout=1800)
            # Find latest output
            mp4s = glob.glob(str(out_dir / "dance_*.mp4"))
            if mp4s:
                latest = max(mp4s, key=os.path.getctime)
                shutil.copy(latest, dest)
                shot["video_file"] = str(dest)
                shot["status"] = "done"
                print(f"\n[OK] 镜头{idx:02d} → {dest.name} ({os.path.getsize(dest)/(1024*1024):.1f}MB, {time.time()-t0:.0f}s)")
                break
            else:
                print(f"  [RETRY] attempt {attempt+1}")
                # Modify prompt slightly on retry
                prompt = prompt.replace("打斗","对峙").replace("杀死","击败")
                cmd[cmd.index("--prompt")+1] = prompt
        else:
            shot["status"] = "failed"
            shot["error"] = "generation failed after retries"
            print(f"[FAIL] 镜头{idx:02d}")

        # Save project state after each shot
        from drama import save_project
        save_project(project)
