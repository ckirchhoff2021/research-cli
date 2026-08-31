import json
import argparse

import os
from common import ChatModel, ensure_optimizer_api_config


def rewrite_skill(args):
    if len(args.selected_patches) == 0:
        output_dir = os.path.dirname(os.path.abspath(args.output_file))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(args.output_file, "w", encoding="utf-8") as file:
            file.write(args.skill_md)
        print(f"skill md saved to {args.output_file}")
        return args.skill_md

    optimizer_api = ensure_optimizer_api_config()
    model = ChatModel(
        optimizer_api["OPTIMIZER_API_URL"],
        optimizer_api["OPTIMIZER_API_KEY"],
        optimizer_api["OPTIMIZER_MODEL_NAME"],
        args.enable_thinking,
    )

    edits_text = json.dumps(args.selected_patches, ensure_ascii=False, indent=2)
    
    query = args.rewrite_template.format(args.skill_md, edits_text)
    try:
        try:
            # use responses first
            skill_md = model.responses(query)
        except Exception as e:
            # use chat completion second
            print(f"responses api failed, fallback to chat_completion, err={e}")
            skill_md = model.chat_completion(query)
    except Exception as outer_e:
        print(f"Both responses and chat_completion failed, err={outer_e}")
        raise RuntimeError("Failed to generate the candidate SKILL.md") from outer_e
    
    if not isinstance(skill_md, str) or not skill_md.strip():
        raise RuntimeError("Rewrite model returned an empty candidate SKILL.md")
    
    output_dir = os.path.dirname(os.path.abspath(args.output_file))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output_file, "w", encoding="utf-8") as file:
        file.write(skill_md)
        
    print(f"skill md saved to {args.output_file}")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="rewrite a skill md")
    parser.add_argument("--enable_thinking", action="store_true", help="Enable thinking in the model")
    parser.add_argument("--rewrite_template", type=str, required=True, help="Path to the rewrite template file")
    
    parser.add_argument("--selected_patches", type=str, required=True, help="Path to the selected patches file")
    
    parser.add_argument("--skill_md", type=str, required=True, help="The newest skill md file")
    parser.add_argument("--output_file", type=str, required=True, help="The output file to save the skill md")
    
    args = parser.parse_args()
    rewrite_template_path = os.path.abspath(args.rewrite_template)
    if not os.path.isfile(rewrite_template_path):
        raise FileNotFoundError(
            f"rewrite_template must be a file path, got: {args.rewrite_template}"
        )
    with open(rewrite_template_path, "r", encoding="utf-8") as file:
        args.rewrite_template = file.read().strip()
        
    with open(args.skill_md, "r", encoding="utf-8") as file:
        args.skill_md = file.read().strip()
        
    with open(args.selected_patches, "r", encoding="utf-8") as file:
        args.selected_patches = json.load(file)
    rewrite_skill(args)
