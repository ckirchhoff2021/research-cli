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


def merge_patches(args):
    all_patches = args.failure_patches + args.success_patches
    
    if len(all_patches) == 0:
        save_patches([], args.output_file)
        print(f"merged patches saved to {args.output_file}")
        return []
    
    optimizer_api = ensure_optimizer_api_config()
    model = ChatModel(
        optimizer_api["OPTIMIZER_API_URL"],
        optimizer_api["OPTIMIZER_API_KEY"],
        optimizer_api["OPTIMIZER_MODEL_NAME"],
        args.enable_thinking,
    )
    patches_text = "\n\n".join([gen_patch_text(i, p) for i, p in enumerate(all_patches)])
    query = args.aggregate_template.format(args.skill_md, patches_text)

    try:
        try:
            # use responses first
            patches = model.responses(query)
        except Exception as e:
            # use chat completion second
            print(f"responses api failed, fallback to chat_completion, err={e}")
            patches = model.chat_completion(query)
    except Exception as outer_e:
        print(f"Both responses and chat_completion failed, err={outer_e}")
        patches = ''
    
    raw_patches = patches.strip() if isinstance(patches, str) else ""
    if len(raw_patches) == 0:
        print("no valid merged patches is generated.")
        save_patches([], args.output_file)
        return []
    
    parsed_patches = _parse_patches(raw_patches, 'merged')
    if len(parsed_patches) == 0:
        raise ValueError(
            f"model returned non-empty merged patches but no parseable patch blocks: {raw_patches[:200]!r}"
        )
    save_patches(parsed_patches, args.output_file)
        
    print(f"merged patches saved to {args.output_file}")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a skill model")
    parser.add_argument("--enable_thinking", action="store_true", help="Enable thinking in the model")
    parser.add_argument("--aggregate_template", type=str, required=True, help="Path to the aggregate template file")
    
    parser.add_argument("--success_patches", type=str, required=True, help="Path to the success patches file")
    parser.add_argument("--failure_patches", type=str, required=True, help="Path to the failure patches file")
    
    parser.add_argument("--skill_md", type=str, required=True, help="The newest skill md file")
    parser.add_argument("--output_file", type=str, required=True, help="The output file to save the merged patches")
   
    args = parser.parse_args()
    aggregate_template_path = os.path.abspath(args.aggregate_template)
    
    if not os.path.isfile(aggregate_template_path):
        raise FileNotFoundError(
            f"aggregate_template must be a file path, got: {args.aggregate_template}"
        )
    with open(aggregate_template_path, "r", encoding="utf-8") as file:
        args.aggregate_template = file.read().strip()
        
    with open(args.skill_md, "r", encoding="utf-8") as file:
        args.skill_md = file.read().strip()
        
    with open(args.success_patches, "r", encoding="utf-8") as file:
        args.success_patches = json.load(file)
        
    with open(args.failure_patches, "r", encoding="utf-8") as file:
        args.failure_patches = json.load(file)
    merge_patches(args)
