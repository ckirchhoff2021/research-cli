"""LLM创作链路：concept → 剧本 + 角色 + 分镜（含对白prompt）。"""
from __future__ import annotations
import json, re
from pathlib import Path

SCRIPT_SYSTEM = """你是资深剧情短视频编剧，精通短片创作和AI视频生成的分镜设计。请严格按以下方法论创作：

【创作方法论】
1. 黄金三秒：第一个镜头必须有视觉或情绪钩子，禁止缓慢铺垫。
2. 角色克制：主要角色2-3个，每人有鲜明外观特征和记忆点。
3. 外观锁定：每个角色必须有完整外观描述（年龄/发型发色/服装配色/配饰/体态/气质），一段话说全，用于AI视频生成时的角色一致性。
4. 分镜节奏：每段10秒，包含场景建立(2-3s) + 人物表演+对白(5-7s)，动作与对白对应。
5. 对白自然：通过自然对话推进故事和表达主题，不用旁白说教；对白要简短有力，每句不超20字。
6. 哲思融入：主题哲理通过角色对话和故事结局自然展现。
7. 视觉先行：动作描写要具体到"人物表情变化、肢体动作、镜头运动"，便于AI视频生成。
8. 审核规避：不写血腥暴力直白打斗，改为"对峙/切磋/剑舞交错/张力氛围"。

输出要求：只输出一个JSON对象（不要markdown栅栏，不要其他文字）：
{
  "title": "片名",
  "genre": "题材标签（古风武侠/现代都市/悬疑/治愈/科幻等）",
  "logline": "一句话梗概",
  "theme": "想表达的核心哲思或情感",
  "style_anchor": "全片统一视觉风格描述（色调/质感/光感/运镜基调，一段完整的话，将被逐镜前置到prompt中）",
  "bgm_style": "gufeng/business/travel/epic/bright/suspense",
  "characters": [
    {
      "name": "角色名",
      "role": "主角/伙伴/对手",
      "appearance": "完整外观描述：年龄段、发型、发色、服装配色与款式、配饰、体态气质，一段连贯的话（将逐字复制到每个镜头prompt）",
      "tag": "记忆点标签",
      "voice_hint": "音色建议（清朗青年男声/英气少女/冷峻男声/温柔女声/磁性旁白等）"
    }
  ],
  "shots": [
    {
      "index": 1,
      "title": "镜头标题（情绪节拍）",
      "scene": "场景地点+光线+环境细节",
      "characters": ["出场角色名"],
      "action": "详细画面动作描述：人物动作、表情变化、肢体语言，必须包含对白时的表演（如"微微一笑说道""转头望向远方平静地说""仰头大笑"），以及镜头运动方式",
      "emotion": "情绪（孤独/轻松/紧张/豁达/顿悟/豪迈）",
      "dialogues": [
        {"character": "角色名", "text": "对白内容（简短有力）", "start_offset": 3.0}
      ]
    }
  ]
}
注意：
- start_offset 是该对白在镜头开始后第几秒说（0-8，给画面留2-3秒铺垫时间）
- 最后一个镜头要有收尾感，或余味悠长
- 所有对白要自然口语化，避免书面腔
"""

VOICE_MAP = {
    "清朗": "ICL_zh_male_zhangjianxiake_tob",
    "侠客": "ICL_zh_male_zhangjianxiake_tob",
    "俊逸": "ICL_zh_male_zhangjianxiake_tob",
    "公子": "ICL_zh_male_zhangjianxiake_tob",
    "青年": "zh_male_yangguangqingnian_moon_bigtts",
    "阳光": "zh_male_yangguangqingnian_moon_bigtts",
    "冷峻": "ICL_zh_male_gugaogongzi_tob",
    "孤傲": "ICL_zh_male_gugaogongzi_tob",
    "深沉": "ICL_zh_male_shenchenzongcai_tob",
    "少女": "zh_female_gufengshaoyu_mars_bigtts",
    "英气": "zh_female_gufengshaoyu_mars_bigtts",
    "少御": "zh_female_gufengshaoyu_mars_bigtts",
    "旁白": "zh_male_jieshuonansheng_mars_bigtts",
    "解说": "zh_male_jieshuonansheng_mars_bigtts",
    "磁性": "zh_male_jieshuonansheng_mars_bigtts",
}

def pick_voice(hint: str) -> str:
    for key, vid in VOICE_MAP.items():
        if key in (hint or ""):
            return vid
    return "ICL_zh_male_zhangjianxiake_tob"

def call_llm(system_prompt, user_prompt, settings):
    """Call Ark LLM and return parsed JSON."""
    from volcenginesdkarkruntime import Ark
    client = Ark(base_url=settings["ark_base_url"], api_key=settings["ark_api_key"])
    resp = client.chat.completions.create(
        model=settings["llm_model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
    )
    text = resp.choices[0].message.content.strip()
    # Strip markdown fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)

def generate_script(concept, num_shots, style, ratio, resolution, settings):
    """Generate full script from concept."""
    user = f"""创意/主题：{concept}
风格倾向：{style}
画面比例：{ratio}，分辨率：{resolution}
请生成{num_shots}个分镜，每个分镜时长10秒，总时长约{num_shots*10}秒。
注意：
- 对白start_offset要合理，第一个对白从2-3秒后开始（先让观众看到场景和人物）
- 相邻镜头场景过渡要自然（外景→内景、昼→夜等变化要合理）
- 每个镜头的action必须描写人物说话时的表情动作，确保AI视频生成时人物有对应的表演"""
    data = call_llm(SCRIPT_SYSTEM, user, settings)

    # Assign voice types to characters
    for c in data.get("characters", []):
        c["voice_type"] = pick_voice(c.get("voice_hint", ""))

    return data

def build_shot_prompts(script_data):
    """Build final video generation prompt for each shot, with style anchor + character appearance lock."""
    style_anchor = script_data.get("style_anchor", "")
    char_map = {c["name"]: c["appearance"] for c in script_data.get("characters", [])}
    shots = script_data.get("shots", [])
    prompts = []
    for shot in shots:
        chars_desc = []
        for cn in shot.get("characters", []):
            app = char_map.get(cn, "")
            if app:
                chars_desc.append(f"{cn}（{app}）")
        char_str = "；".join(chars_desc)
        dialogue_desc = ""
        for d in shot.get("dialogues", []):
            dialogue_desc += f'{d["character"]}说{d["text"]}时表情生动口型自然，' 
        prompt = f"{style_anchor}。{char_str}。场景：{shot['scene']}。画面：{shot['action']}。{dialogue_desc}情绪氛围：{shot.get('emotion','自然')}。"
        prompts.append(prompt)
        shot["prompt"] = prompt
    return shots

def d_action_hint(char, action):
    """Extract dialogue performance hint from action text."""
    return "表情生动口型自然"

def render_script_md(script_data):
    lines = [f"# {script_data.get('title','短剧')}", "",
             f"> 题材：{script_data.get('genre','')} ｜ BGM风格：{script_data.get('bgm_style','')}",
             f"> 梗概：{script_data.get('logline','')}",
             f"> 主题：{script_data.get('theme','')}",
             f"> 风格锚点：{script_data.get('style_anchor','')}", "",
             "## 角色设定", "",
             "| 角色 | 定位 | 记忆点 | 音色 | 外观 |",
             "|---|---|---|---|---|"]
    for c in script_data.get("characters", []):
        lines.append(f"| {c['name']} | {c.get('role','')} | {c.get('tag','')} | {c.get('voice_hint','')} | {c.get('appearance','')} |")
    lines += ["", "## 分镜剧本", ""]
    for s in script_data.get("shots", []):
        lines += [f"### 镜头{s['index']:02d} {s['title']}（{s.get('emotion','')}）",
                  f"- **场景**：{s['scene']}",
                  f"- **角色**：{'、'.join(s.get('characters',[]))}",
                  f"- **动作**：{s['action']}"]
        for d in s.get("dialogues", []):
            lines.append(f"- **{d['character']}**（{d.get('start_offset',2)}s）：{d['text']}")
        lines.append("")
    return "\n".join(lines)
