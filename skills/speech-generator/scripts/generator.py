#!/usr/bin/env python3
import argparse
import subprocess
import os
import sys
import tempfile
from pathlib import Path

COSYVOICE_PATH = "/home/chenxiang.101/workspace/CosyVoice"
VENV_PYTHON = os.path.join(COSYVOICE_PATH, ".venv/bin/python")

def main():
    parser = argparse.ArgumentParser(description="Speech generation wrapper for CosyVoice")
    parser.add_argument("--task_type", required=True, choices=["voice_clone", "cross_lingual_gen", "instruct_gen"], help="Task type")
    parser.add_argument("--tts_text", required=False, help="Text to synthesize (use --tts_file for text longer than 2000 characters)")
    parser.add_argument("--tts_file", required=False, help="Path to text file containing content to synthesize (alternative to --tts_text)")
    parser.add_argument("--prompt_wav", default="./asset/zero_shot_prompt.wav", help="Reference audio path")
    parser.add_argument("--instruct_prompt", default="", help="Instruction prompt for instruct_gen")
    parser.add_argument("--background", action="store_true", default=False, help="Run generation in background (no timeout, suitable for long text)")
    parser.add_argument("--output_file", default="outputs/output.wav", help="Custom output file path (needed in background mode and optional for non-background mode)")
    
    args = parser.parse_args()
    
    # Validate input
    if not args.tts_text and not args.tts_file:
        print("Error: Either --tts_text or --tts_file must be provided", file=sys.stderr)
        sys.exit(1)
    
    # Read text from file if provided
    tts_text = args.tts_text
    if args.tts_file:
        try:
            with open(args.tts_file, 'r', encoding='utf-8') as f:
                tts_text = f.read()
        except Exception as e:
            print(f"Error: Failed to read text file: {str(e)}", file=sys.stderr)
            sys.exit(1)
    
    # Warn about long text
    if len(tts_text) > 2000 and not args.tts_file:
        print("Warning: Text length exceeds 2000 characters, recommend using --tts_file for better stability", file=sys.stderr)
    
    # Build command
    cmd = [
        VENV_PYTHON, "-m", "inference.generator",
        "--task_type", args.task_type,
        "--tts_text", tts_text,
        "--prompt_wav", args.prompt_wav,
        "--save_file", args.output_file
    ]
    if args.task_type == "instruct_gen" and args.instruct_prompt:
        cmd.extend(["--instruct_prompt", args.instruct_prompt])
    
    if args.background:
        # Run in background with nohup
        log_file = os.path.join(COSYVOICE_PATH, "generation.log")
        with open(log_file, 'w') as f:
            subprocess.Popen(cmd, cwd=COSYVOICE_PATH, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        print(f"Generation started in background, check log at {log_file}, output will be saved to {os.path.join(COSYVOICE_PATH, args.output_file)}")
    else:
        # Run synchronously
        result = subprocess.run(cmd, cwd=COSYVOICE_PATH, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error: Generation failed\nStderr: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        
        print(result.stdout)
    
    
if __name__ == "__main__":
    main()
