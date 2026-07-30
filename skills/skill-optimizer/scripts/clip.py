import json
import argparse

import os
from common import ChatModel, gen_patch_text, _parse_patches, ensure_optimizer_api_config


def save_patches(patches, output_file):
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(patches, file, indent=2, ensure_ascii=False)


def gradient_clip(args):
    if len(args.merged_patches) == 0:
        save_patches([], args.output_file)
        print(f"selected patches saved to {args.output_file}")
        return []
    
    if len(args.merged_patches) <= args.edit_budget:
        save_patches(args.merged_patches, args.output_file)
        print(f"selected patches saved to {args.output_file}")
        return args.merged_patches
    
    # 需要裁剪，使用 LLM 排序
    optimizer_api = ensure_optimizer_api_config()
    model = ChatModel(
        optimizer_api["OPTIMIZER_API_URL"],
        optimizer_api["OPTIMIZER_API_KEY"],
        optimizer_api["OPTIMIZER_MODEL_NAME"],
        args.enable_thinking,
    )
    edits_text = "\n\n".join([
        gen_patch_text(i, e)
        for i, e in enumerate(args.merged_patches)
    ])
    
    query = args.clip_template.format(args.edit_budget, args.skill_md, edits_text)
    try:
        try:
            # use responses first
            selected_patches = model.responses(query)
        except Exception as e:
            # use chat completion second
            print(f"responses api failed, fallback to chat_completion, err={e}")
            selected_patches = model.chat_completion(query)
    except Exception as outer_e:
        print(f"Both responses and chat_completion failed, err={outer_e}")
        selected_patches = ''
    
    if len(selected_patches) == 0:
        print("no valid selected patches is generated.")
        save_patches([], args.output_file)
        return []
    
    patches = _parse_patches(selected_patches, 'selected')
    save_patches(patches, args.output_file)
        
    print(f"selected patches saved to {args.output_file}")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a skill model")
    parser.add_argument("--enable_thinking", action="store_true", help="Enable thinking in the model")
    parser.add_argument("--clip_template", type=str, required=True, help="Path to the clip template file")
    
    parser.add_argument("--merged_patches", type=str, required=False, help="Path to the merged patches file")
    parser.add_argument("--edit_budget", type=int, default=5, help="Maximum number of patches to keep")
    
    parser.add_argument("--skill_md", type=str, required=True, help="The newest skill md file")
    parser.add_argument("--output_file", type=str, required=True, help="The output file to save the merged patches")
   
    args = parser.parse_args()
    clip_template_path = os.path.abspath(args.clip_template)
    if not os.path.isfile(clip_template_path):
        raise FileNotFoundError(
            f"clip_template must be a file path, got: {args.clip_template}"
        )
    with open(clip_template_path, "r", encoding="utf-8") as file:
        args.clip_template = file.read().strip()
        
    with open(args.skill_md, "r", encoding="utf-8") as file:
        args.skill_md = file.read().strip()
        
    with open(args.merged_patches, "r", encoding="utf-8") as file:
        args.merged_patches = json.load(file)
    gradient_clip(args)
