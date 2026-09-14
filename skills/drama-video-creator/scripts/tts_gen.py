"""TTS对白配音生成。"""
from __future__ import annotations
import subprocess, os
from pathlib import Path

def generate_all_voices(project, base, venv_py, tts_script, project_root):
    """Generate TTS for all dialogues in all shots."""
    voices_dir = base / "voices"
    voices_dir.mkdir(exist_ok=True)
    chars = {c["name"]: c for c in project.get("script", {}).get("characters", [])}
    shots = project.get("shots", [])

    for si, shot in enumerate(shots):
        dialogues = shot.get("dialogues", [])
        voice_entries = []
        for di, d in enumerate(dialogues):
            char_name = d.get("character", "")
            text = d.get("text", "")
            if not text.strip():
                continue
            char = chars.get(char_name, {})
            voice_type = char.get("voice_type", "ICL_zh_male_zhangjianxiake_tob")
            fname = f"s{si+1:02d}_d{di+1}_{char_name}.mp3"
            out_path = voices_dir / fname
            if not out_path.exists() or os.path.getsize(out_path) < 100:
                print(f"  镜头{si+1:02d} {char_name}: {text[:30]}...", end=" ", flush=True)
                r = subprocess.run(
                    [str(venv_py), str(tts_script),
                     "--tts_text", text,
                     "--voice_type", voice_type,
                     "--output_file", str(out_path)],
                    capture_output=True, text=True, cwd=str(project_root), timeout=120)
                if r.returncode == 0 and out_path.exists():
                    print(f"OK ({os.path.getsize(out_path)/1024:.0f}KB)")
                else:
                    print(f"FAIL")
                    if r.stderr: print(f"    {r.stderr[-200:]}")
            # Get duration
            dur = 0
            if out_path.exists():
                try:
                    from moviepy import AudioFileClip
                    c = AudioFileClip(str(out_path))
                    dur = c.duration
                    c.close()
                except Exception:
                    dur = len(text) * 0.25  # rough estimate
            voice_entries.append({
                "character": char_name,
                "text": text,
                "voice_file": str(out_path),
                "duration": round(dur, 2),
                "start_offset": d.get("start_offset", 2.5),
            })
        shot["voices"] = voice_entries
