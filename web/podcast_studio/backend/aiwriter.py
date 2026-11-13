"""AI 播客编剧：给定主题，调用 Ark LLM 自动生成标题与主播对白。

输出经清洗的 JSON：{"title": ..., "segments": [{"speaker": "A"|"B", "text": ...}]}
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

# ── 节目风格 ─────────────────────────────────────────
STYLES: dict[str, dict] = {
    "chat": {
        "label": "轻松闲聊",
        "directive": "朋友之间轻松聊天的语气，口语化、接地气，可以适当幽默和插科打诨，像真实播客里自然地接话与跑题再拉回。",
    },
    "interview": {
        "label": "深度访谈",
        "directive": "A 是主持人，善于追问；B 是业内资深嘉宾，分享真实经历与独到观点。提问层层深入，回答有细节、有金句。",
    },
    "science": {
        "label": "知识科普",
        "directive": "把复杂的知识讲得通俗易懂，多用生活化的类比和具体例子；主持人替听众提问和质疑，嘉宾负责把概念讲清楚，信息准确有收获。",
    },
    "talkshow": {
        "label": "搞笑脱口秀",
        "directive": "喜剧脱口秀风格，节奏明快、包袱密集，可以夸张吐槽和反转；两人互相接梗，全程轻松好笑。",
    },
    "business": {
        "label": "商业财经",
        "directive": "商业财经对谈，理性客观，结合真实公司案例、数据与趋势分析，观点有依据，避免空泛口号。",
    },
    "story": {
        "label": "情感故事",
        "directive": "温暖治愈的情感电台，以讲故事为主，有具体的人物和情节，情绪细腻有共鸣，结尾给出温柔的感悟。",
    },
}


SYSTEM_PROMPT = """你是一位资深播客编剧，擅长根据主题创作适合“听”的自然口语对白。
硬性要求：
1. 只输出 JSON，不要输出任何解释、开场白或 markdown 代码块。
2. 对白必须是地道的口语：短句为主，避免书面化长句、分点罗列、舞台提示和括号动作说明。
3. 内容结构完整：开场要抓住人，中间有观点/故事/举例和自然的来回，结尾收束并点题。
4. 每段话控制在 15~90 个字，不要让同一个人连续讲太久。
5. JSON 格式严格如下，speaker 只能填 "A" 或 "B"：
{"title":"不超过15个字的吸引人标题","segments":[{"speaker":"A","text":"台词内容"}]}"""


def _build_user(topic: str, style_key: str, turns: int,
                mode: str) -> str:
    style = STYLES.get(style_key, STYLES["chat"])
    topic = topic.strip()
    if mode == "monologue":
        return f"""节目主题：{topic}
节目形式：单人讲述（所有 speaker 都必须是 A），把内容拆成若干段连贯的口播，像是一个人在自然地讲述，而不是念论文。
语言风格：{style['directive']}
请生成约 {turns} 段台词（总字数约 {turns * 55} 字）。"""
    return f"""节目主题：{topic}
节目形式：双人播客对谈。A 是主播，负责开场、提问、串场和总结；B 是嘉宾，负责输出观点、故事和金句。
语言风格：{style['directive']}
请生成约 {turns} 段对白（A、B 交替，总字数约 {turns * 45} 字）。"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 兜底：截取首个 { 到末个 }
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)
    return json.loads(text)


def generate_dialogue(topic: str, style_key: str = "chat",
                      turns: int = 12, mode: str = "dialogue",
                      log=None) -> dict:
    """生成播客对白。返回 {title, segments:[{speaker,text}]}。"""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("请先输入节目主题")
    if len(topic) > 200:
        raise ValueError("主题请控制在 200 字以内")
    turns = max(4, min(40, int(turns)))
    if mode not in ("dialogue", "monologue"):
        mode = "dialogue"

    if log:
        log(f"🤖 AI 编剧启动｜主题：{topic[:40]}")
        log(f"   风格：{STYLES.get(style_key, STYLES['chat'])['label']}"
            f"｜形式：{'单人讲述' if mode == 'monologue' else '双人对谈'}"
            f"｜约 {turns} 段")

    from volcenginesdkarkruntime import Ark

    base_url = os.getenv("ARK_BASE_URL",
                         "https://ark.cn-beijing.volces.com/api/v3")
    api_key = os.getenv("BRAIN_API_KEY") or os.getenv("ARK_API_KEY")
    model = os.getenv("BRAIN_MODEL_NAME", "doubao-pro-32k")
    if not api_key:
        raise RuntimeError("未配置 BRAIN_API_KEY，无法使用 AI 编剧")

    client = Ark(base_url=base_url, api_key=api_key, timeout=180)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user(
                topic, style_key, turns, mode)},
        ],
        temperature=0.85,
        max_tokens=4096,
    )
    raw = resp.choices[0].message.content
    data = _parse_json(raw)

    title = str(data.get("title") or topic).strip()[:30]
    segs = data.get("segments") or []
    clean = []
    for s in segs:
        if not isinstance(s, dict):
            continue
        speaker = str(s.get("speaker", "")).strip().upper()
        text = str(s.get("text", "")).strip()
        if speaker not in ("A", "B") or not text:
            continue
        if mode == "monologue":
            speaker = "A"
        clean.append({"speaker": speaker, "text": text})
    if len(clean) < 3:
        raise RuntimeError("AI 返回的有效台词过少，请重试或换个主题")

    if log:
        log(f"✍ 生成完成：《{title}》共 {len(clean)} 段"
            f"（{sum(len(s['text']) for s in clean)} 字）")
    return {"title": title, "segments": clean}
