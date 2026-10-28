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
      "gender": "性别（男/女）",
      "voice_hint": "音色建议（清朗青年男声/英气少女/冷峻男声/温柔女声/御姐女声/磁性旁白等，必须与gender一致）"
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

DEFAULT_MALE_VOICE = "ICL_zh_male_zhangjianxiake_tob"
DEFAULT_FEMALE_VOICE = "zh_female_wenrouxiaoya_moon_bigtts"

MALE_VOICE_MAP = {
    "少年": "ICL_zh_male_shuanglangshaonian_tob",
    "爽朗": "ICL_zh_male_shuanglangshaonian_tob",
    "年轻": "ICL_zh_male_shuanglangshaonian_tob",
    "侠客": "ICL_zh_male_zhangjianxiake_tob",
    "清朗": "ICL_zh_male_shuanglangshaonian_tob",
    "俊逸": "ICL_zh_male_yangyang_v1_tob",
    "公子": "ICL_zh_male_zhangjianxiake_tob",
    "青年": "zh_male_yangguangqingnian_moon_bigtts",
    "阳光": "zh_male_yangguangqingnian_moon_bigtts",
    "冷峻": "ICL_zh_male_lengjungaozhi_tob",
    "高手": "ICL_zh_male_lengjungaozhi_tob",
    "冷漠": "ICL_zh_male_lengjungaozhi_tob",
    "孤傲": "ICL_zh_male_gugaogongzi_tob",
    "深沉": "zh_male_bv139_audiobook_ummv3_bigtts",
    "沉稳": "zh_male_bv139_audiobook_ummv3_bigtts",
    "中年": "ICL_zh_male_lengjungaozhi_tob",
    "老者": "zh_male_bv139_audiobook_ummv3_bigtts",
    "老翁": "zh_male_bv139_audiobook_ummv3_bigtts",
    "旁白": "zh_male_jieshuonansheng_mars_bigtts",
    "解说": "zh_male_jieshuonansheng_mars_bigtts",
    "磁性": "zh_male_jieshuonansheng_mars_bigtts",
}

FEMALE_VOICE_MAP = {
    # 老年女性优先（关键词更具体，放在前面）
    "婆婆": "ICL_zh_female_heainainai_tob",
    "奶奶": "ICL_zh_female_heainainai_tob",
    "老妇": "ICL_zh_female_heainainai_tob",
    "老奶奶": "ICL_zh_female_heainainai_tob",
    # 御姐/成熟
    "御姐": "zh_female_gaolengyujie_moon_bigtts",
    "高冷": "zh_female_gaolengyujie_moon_bigtts",
    "清冷": "zh_female_gaolengyujie_moon_bigtts",
    "冷艳": "ICL_zh_female_wumeiyujie_tob",
    "妩媚": "ICL_zh_female_wumeiyujie_tob",
    "成熟": "ICL_zh_female_chengshujiejie_tob",
    "姐姐": "ICL_zh_female_chengshujiejie_tob",
    "女王": "ICL_zh_female_jiaohannvwang_tob",
    "太后": "ICL_zh_female_jiaohannvwang_tob",
    "皇后": "ICL_zh_female_jiaohannvwang_tob",
    "贵妃": "ICL_zh_female_jiaohannvwang_tob",
    "夫人": "ICL_zh_female_chengshujiejie_tob",
    # 少女/年轻女性
    "少女": "zh_female_gufengshaoyu_mars_bigtts",
    "古风": "zh_female_gufengshaoyu_mars_bigtts",
    "少御": "zh_female_gufengshaoyu_mars_bigtts",
    "英气": "zh_female_gufengshaoyu_mars_bigtts",
    "仙女": "zh_female_gufengshaoyu_mars_bigtts",
    "柔弱": "ICL_zh_female_bingruoshaonv_tob",
    "病弱": "ICL_zh_female_bingruoshaonv_tob",
    "清纯": "ICL_zh_female_chunzhenshaonv_e588402fb8ad_tob",
    "纯真": "ICL_zh_female_chunzhenshaonv_e588402fb8ad_tob",
    # 活泼/甜美
    "活泼": "ICL_zh_female_huoponvhai_tob",
    "俏皮": "ICL_zh_female_huopodiaoman_tob",
    "开朗": "zh_female_kailangjiejie_moon_bigtts",
    "爽快": "zh_female_shuangkuaisisi_moon_bigtts",
    "元气": "zh_female_yuanqinvyou_moon_bigtts",
    "可爱": "ICL_zh_female_keainvsheng_tob",
    "萝莉": "ICL_zh_female_jiaoruoluoli_tob",
    "撒娇": "zh_female_sajiaonvyou_moon_bigtts",
    "甜美": "zh_female_tianmeixiaoyuan_moon_bigtts",
    "甜蜜": "zh_female_tianmeixiaoyuan_moon_bigtts",
    "娇蛮": "ICL_zh_female_bingjiaomengmei_tob",
    # 温柔（默认女声风格）
    "温柔": "zh_female_wenrouxiaoya_moon_bigtts",
    "温婉": "ICL_zh_female_wenrouwenya_tob",
    "文雅": "ICL_zh_female_wenrouwenya_tob",
    "知性": "ICL_zh_female_zhixingwenwan_tob",
    "贴心": "ICL_zh_female_nuanxinxuejie_tob",
    "和蔼": "ICL_zh_female_heainainai_tob",
    "苍老": "ICL_zh_female_heainainai_tob",
}

# 兼容旧引用：合并表（女声在前，含“女”的通用词单独由 pick_voice 处理）
VOICE_MAP = {**FEMALE_VOICE_MAP, **MALE_VOICE_MAP}

# 仅凭一个字就能判定性别的兜底关键词
_FEMALE_HINT_WORDS = ("女", "娘", "妇", "妪", "姬", "妃", "妣", "奶奶", "婆婆", "姐", "妹", "姑娘", "千金", "太后")


def infer_gender(char: dict) -> str:
    """从角色字段判断性别，返回 '女'/'男'/''。"""
    g = str(char.get("gender", "")).strip()
    if "女" in g:
        return "女"
    if "男" in g:
        return "男"
    hint = str(char.get("voice_hint", ""))
    if any(w in hint for w in _FEMALE_HINT_WORDS):
        return "女"
    if "男声" in hint or "男生" in hint:
        return "男"
    name = str(char.get("name", ""))
    if any(w in name for w in ("阿姨", "大娘", "姑娘", "奶奶", "婆婆", "姐", "妹", "娘", "太后", "贵妃")):
        return "女"
    return ""


def pick_voice(hint: str, gender: str = "") -> str:
    """按音色提示词选 voice_type；gender 明确时优先匹配同性别音色，避免女角色落男声。"""
    hint = hint or ""
    g = "女" if "女" in (gender or "") else ("男" if "男" in (gender or "") else "")
    # 性别明确时只在同性音色表里匹配，保证不会男女错位
    table = (
        FEMALE_VOICE_MAP if g == "女"
        else MALE_VOICE_MAP if g == "男"
        else VOICE_MAP
    )
    for key, vid in table.items():
        if key in hint:
            return vid
    # 无任何关键词命中：按性别兜底
    if g == "女":
        return DEFAULT_FEMALE_VOICE
    if g == "男":
        return DEFAULT_MALE_VOICE
    # 性别未知：提示词里含女性称谓也走女声
    if any(w in hint for w in _FEMALE_HINT_WORDS):
        return DEFAULT_FEMALE_VOICE
    return DEFAULT_MALE_VOICE

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

    # Assign voice types to characters（传入性别，防止女角色落男声）
    for c in data.get("characters", []):
        c["voice_type"] = pick_voice(c.get("voice_hint", ""), c.get("gender", ""))

    return data


def refine_script(concept, prev_script, feedback, ratio, resolution, settings):
    """结合上一版剧本与用户反馈，让 LLM 调整并输出完整新剧本（保持相同 JSON 格式）。"""
    import json as _json
    user = f"""原始创意：{concept}
画面比例：{ratio}，分辨率：{resolution}

这是上一版剧本：
{_json.dumps(prev_script, ensure_ascii=False)}

用户的修改反馈：
{feedback}

请严格依据用户反馈调整剧本：反馈点到的内容必须修改，未提及的内容尽量保持不变。
仍然输出完整 JSON（格式与上一版一致，包含全部角色与分镜），不要只输出改动片段。
若用户要求增减分镜，请相应调整；角色外观描述仍需完整，用于视频生成的一致性。"""
    data = call_llm(SCRIPT_SYSTEM, user, settings)
    for c in data.get("characters", []):
        c["voice_type"] = pick_voice(c.get("voice_hint", ""), c.get("gender", ""))
    return data

SHOT_SYSTEM = """你是资深剧情短视频编剧，正在为一部已经存在的短剧补充分镜。请严格按以下要求创作一个镜头：

【创作要求】
1. 只输出一个JSON对象（不要markdown栅栏，不要其他文字）：
{
  "title": "镜头标题（情绪节拍）",
  "scene": "场景地点+光线+环境细节",
  "action": "详细画面动作描述：人物动作、表情变化、肢体语言、对白时的表演，以及镜头运动方式",
  "emotion": "情绪氛围（如孤独/轻松/紧张/豁达/顿悟/豪迈）",
  "duration": 10,
  "characters": ["出场角色名，只能使用用户消息中列出的已有角色"],
  "dialogues": [
    {"character": "角色名", "text": "对白内容（简短自然，每句不超20字）", "start_offset": 3.0}
  ]
}
2. characters 字段只能填写已有角色名，不要创造新角色；没有人物出场时填写 []。
3. dialogues 中的 character 必须出现在 characters 中；该镜头不需要对白时 dialogues 填 []。
4. start_offset 为该对白在镜头开始后第几秒（0-8，先给画面留2-3秒铺垫）。
5. 新镜头的场景时间线要与已有分镜衔接自然（外景→内景、昼→夜等变化要合理），并符合全片视觉基调。
6. 不写血腥暴力直白打斗，改为"对峙/切磋/剑舞交错/张力氛围"。
"""

def generate_shot(user_prompt, context, settings):
    """Generate one shot JSON from the user's prompt, grounded in the existing project."""
    import json as _json
    style_anchor = context.get("style_anchor", "")
    characters = context.get("characters", [])
    prev_shots = context.get("shots", [])

    char_lines = "\n".join(f"- {c.get('name','')}：{c.get('appearance','')}" for c in characters) or "- （暂无角色）"
    shot_lines = "\n".join(f"{i+1}. {s.get('title','')} — {s.get('scene','')}" for i, s in enumerate(prev_shots)) or "- （暂无分镜）"

    user = f"""全片视觉基调：{style_anchor}

已有角色：
{char_lines}

已有分镜（新镜头需与之衔接）：
{shot_lines}

用户对新镜头的描述：
{user_prompt}

请据此创作这一个镜头，只输出 JSON 对象。"""
    data = call_llm(SHOT_SYSTEM, user, settings)

    # 兜底清洗：characters/dialogues 只能引用已有角色，duration 取整到 4-10 秒
    valid_names = {c.get("name", "") for c in characters}
    data["characters"] = [n for n in data.get("characters", []) if n in valid_names]
    clean_dialogues = []
    for d in data.get("dialogues", []):
        if isinstance(d, dict) and d.get("character") in valid_names and d.get("text", "").strip():
            clean_dialogues.append({
                "character": d["character"],
                "text": str(d["text"]).strip(),
                "start_offset": float(d.get("start_offset", 2.5) or 2.5),
            })
    data["dialogues"] = clean_dialogues
    try:
        data["duration"] = max(4, min(10, int(data.get("duration", 10) or 10)))
    except (TypeError, ValueError):
        data["duration"] = 10
    for key in ("title", "scene", "action", "emotion"):
        data.setdefault(key, "")
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
