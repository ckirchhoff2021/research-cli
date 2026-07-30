import json
import os
import re
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")

BRAIN_ENV_KEYS = (
    "BRAIN_API_KEY",
    "BRAIN_API_URL",
    "BRAIN_MODEL_NAME",
)
OPTIMIZER_ENV_KEYS = (
    "OPTIMIZER_API_KEY",
    "OPTIMIZER_API_URL",
    "OPTIMIZER_MODEL_NAME",
)


def load_local_env(override: bool = False) -> None:
    """Load the skill-local .env file instead of relying on the workspace root."""
    load_dotenv(dotenv_path=ENV_FILE, override=override)


def _env_purpose(group_name: str) -> str:
    if group_name == "BRAIN_API":
        return "用于在 Harness 环境中执行目标 Skill"
    return "用于评测和优化目标 Skill"



def _print_env_setup_hint(group_name: str, missing_keys: List[str]) -> None:
    print(
        f"{group_name} 配置缺失：{', '.join(missing_keys)}。"
        f"{group_name} {_env_purpose(group_name)}。"
    )
    if not os.path.isfile(ENV_FILE):
        print(f"首次运行请先在 {ENV_FILE} 中补齐对应配置。")
    print(f"补齐 {ENV_FILE} 后重新运行当前命令。")


def ensure_api_group(group_name: str, env_keys: tuple[str, ...]) -> Dict[str, str]:
    """Ensure the required API settings exist, prompting and persisting when needed."""
    load_local_env()
    values = {key: os.getenv(key, "").strip() for key in env_keys}
    missing_keys = [key for key, value in values.items() if not value]
    if not missing_keys:
        return values

    _print_env_setup_hint(group_name, missing_keys)
    raise RuntimeError(
        f"{group_name} 配置不完整，请在 {ENV_FILE} 中补齐：{', '.join(missing_keys)}"
    )


def ensure_brain_api_config() -> Dict[str, str]:
    return ensure_api_group("BRAIN_API", BRAIN_ENV_KEYS)


def ensure_optimizer_api_config() -> Dict[str, str]:
    return ensure_api_group("OPTIMIZER_API", OPTIMIZER_ENV_KEYS)


class ChatModel:
    def __init__(self, base_url, api_key, model_name, enable_thinking=False):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name
        self.enable_thinking = enable_thinking
        
    def responses(self, text_input, system_prompt="", temperature=0.7):
        extra = {"thinking": {"type": "enabled"}} if self.enable_thinking else {"thinking": {"type": "disabled"}}
        response = self.client.responses.create(
            model=self.model_name,
            instructions=system_prompt if system_prompt else "",
            input=text_input,
            temperature=temperature,
            reasoning={"effort": "medium"} if self.enable_thinking else None,
            extra_body=extra,
        )
        
        return response.output_text
        
    def chat_completion(self, text_input, system_prompt="", temperature=0.7):
        messages = []
        if system_prompt and len(system_prompt) > 0:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text_input})
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            extra_body={"chat_template_kwargs": {"enable_thinking": self.enable_thinking}}
        )

        return response.choices[0].message.content


def gen_patch_text(index: int, patch: Dict[str, Any]) -> str:
    """Generate structured patch text for LLM processing."""
    if "edits" not in patch:
        patch = {
            "type": patch.get("type", "N/A"),
            "reason": patch.get("reason", ""),
            "edits": [{
                key: value
                for key, value in patch.items()
                if key in {"op", "anchor", "target", "content"}
            }],
        }
    return f"### Patch {index + 1}\n{json.dumps(patch, ensure_ascii=False, indent=2)}"


def _parse_patches(text: str, patch_type: str) -> List[Dict[str, Any]]:
    """解析 LLM 输出的 patch 格式为结构化数据"""
    patches = []
    
    # 提取 <patch>...</patch> 块
    patch_blocks = re.findall(r'<patch>(.*?)</patch>', text, re.DOTALL)
    if not patch_blocks:
        return patches
    
    for block in patch_blocks:
        edits = re.findall(r'<edit op="(\w+)">(.*?)</edit>', block, re.DOTALL)
        reason_match = re.search(r'<edit_reason>(.*?)</edit_reason>', block, re.DOTALL)
        reason = reason_match.group(1).strip() if reason_match else ""
        patch = {
            "type": patch_type,
            "reason": reason,
            "edits": [],
        }

        for op, content in edits:
            anchor_match = re.search(r'<anchor>(.*?)</anchor>', content, re.DOTALL)
            content_match = re.search(r'<content>(.*?)</content>', content, re.DOTALL)
            target_match = re.search(r'<target>(.*?)</target>', content, re.DOTALL)
            
            edit = {
                "op": op,
            }
            
            if anchor_match:
                edit["anchor"] = anchor_match.group(1).strip()
            if content_match:
                edit["content"] = content_match.group(1).strip()
            if target_match:
                edit["target"] = target_match.group(1).strip()

            patch["edits"].append(edit)

        if patch["edits"]:
            patches.append(patch)
    
    return patches
