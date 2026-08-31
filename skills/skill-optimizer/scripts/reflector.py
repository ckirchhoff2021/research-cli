import json
import argparse
import os
import random
from common import ChatModel, _parse_patches, ensure_optimizer_api_config


def save_patches(patches, output_file):
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(patches, file, indent=2, ensure_ascii=False)


def reflect(args):
    with open(args.cases_file, "r", encoding="utf-8") as file:
        cases = json.load(file)
    if len(cases) == 0:
        save_patches([], args.output_file)
        print(f"patches saved to {args.output_file}")
        return []

    optimizer_api = ensure_optimizer_api_config()
    model = ChatModel(
        optimizer_api["OPTIMIZER_API_URL"],
        optimizer_api["OPTIMIZER_API_KEY"],
        optimizer_api["OPTIMIZER_MODEL_NAME"],
        args.enable_thinking,
    )
    random.shuffle(cases)
    
    used_cases = cases
    if len(cases) > 5:
        used_cases = cases[:5]

    case_str = ''
    for i, case in enumerate(used_cases):
        case_str += f"Case {i+1}:\n"
        case_str += json.dumps(case, ensure_ascii=False, indent=2) + '\n'
        
    query = args.reflect_template.format(
        skill_md=args.skill_md,
        rejected_patches=args.rejected_patches,
        cases=case_str
    )

    try:
        try:
            # use responses first
            patches = model.responses(query, args.system_prompt)
        except Exception as e:
            # use chat completion second
            print(f"responses api failed, fallback to chat_completion, err={e}")
            patches = model.chat_completion(query, system_prompt=args.system_prompt)
    except Exception as outer_e:
        print(f"Both responses and chat_completion failed, err={outer_e}")
        patches = ''
    
    raw_patches = patches.strip() if isinstance(patches, str) else ""
    if len(raw_patches) == 0:
        print("no valid patches is generated.")
        save_patches([], args.output_file)
        return []
    
    parsed_patches = _parse_patches(raw_patches, args.case_type)
    if len(parsed_patches) == 0:
        raise ValueError(
            f"model returned non-empty patches but no parseable patch blocks: {raw_patches[:200]!r}"
        )
    save_patches(parsed_patches, args.output_file)
        
    print(f"patches saved to {args.output_file}")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a skill model")
    parser.add_argument("--enable_thinking", action="store_true", help="Enable thinking in the model")
    parser.add_argument("--system_prompt", type=str, required=False, help="The system prompt to use for the model")
    parser.add_argument("--cases_file", type=str, required=True, help="The cases file to use for reflect")
    parser.add_argument("--reflect_template", type=str, required=True, help="Path to the reflect template file")
    parser.add_argument("--rejected_patches", type=str, required=True, help="Path to the rejected patches file")
    parser.add_argument("--skill_md", type=str, required=True, help="The newest skill md file")
    parser.add_argument("--case_type", type=str, required=True, help="The case type")
    parser.add_argument("--output_file", type=str, required=True, help="The output file to save the patches")
   
    args = parser.parse_args()
    reflect_template_path = os.path.abspath(args.reflect_template)
    if not os.path.isfile(reflect_template_path):
        raise FileNotFoundError(
            f"reflect_template must be a file path, got: {args.reflect_template}"
        )
    with open(reflect_template_path, "r", encoding="utf-8") as file:
        args.reflect_template = file.read().strip()
        
    with open(args.skill_md, "r", encoding="utf-8") as file:
        args.skill_md = file.read().strip()
        
    rejected_patches_path = os.path.abspath(args.rejected_patches)
    if not os.path.isfile(rejected_patches_path):
        save_patches([], rejected_patches_path)
    with open(rejected_patches_path, "r", encoding="utf-8") as file:
        args.rejected_patches = file.read().strip()
    reflect(args)
