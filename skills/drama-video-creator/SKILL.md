---
name: drama-video-creator
description: 剧情短视频创作技能，支持从一句话创意自动生成带对白配音和背景音乐的完整剧情短片。自动完成「创意→剧本（含角色设定）→分镜表（含角色外观锁定防漂移）→角色参考图→对白配音（多角色音色）→视频片段生成→BGM合成→音画精确对齐拼接成片」全流程。当用户要求创作剧情短视频、短剧、带对白的故事视频、AI微电影、武侠/都市/古风剧情片时必须使用本技能。用户提及"剧本+视频+配音/对白/声音/台词/说话"时触发。
---

# drama-video-creator 剧情短视频创作技能

## 概述
本技能将 LLM 剧本创作、TTS 配音、AI 视频生成、BGM 合成、ffmpeg 音画对齐拼接整合为全自动流水线，输出带多角色对白配音和背景音乐的完整剧情短片（1-2分钟）。

## 核心能力
1. **智能剧本**：基于短剧创作方法论（黄金三秒/爆点五段式/三类钩子）由 LLM 生成结构化剧本，含角色外观锁定段
2. **角色一致性**：自动为每个角色生成 CG 风格参考图；分镜 prompt 逐字复制角色外观描述防止镜头间人物漂移
3. **多角色配音**：使用 speech-generator 为每个角色匹配不同音色，生成对白音频，获取精确时长
4. **音画同步**：先生成配音确定时长，再生成视频片段（prompt 包含对白对应的动作/表情/口型提示），最后精确对齐
5. **风格化BGM**：根据题材自动合成匹配的背景音乐（古风/现代/悬疑/欢快/史诗），对白时自动降音（ducking）
6. **智能拼接**：ffmpeg xfade 交叉淡入淡出转场 + 片头片尾字幕卡片
7. **断点续跑**：项目状态原子持久化，中断后重跑自动跳过已完成步骤
8. **审核规避**：内置敏感内容规避策略（不用真人照片参考、打斗改为切磋/张力描写）

## 依赖
- Python 环境：项目 `.venv/bin/python`
- 依赖包：moviepy, Pillow, numpy, scipy, imageio-ffmpeg, volcenginesdkarkruntime, dotenv, httpx
- 调用项目内其他技能：`image-generator`（角色参考图）、`video-generator`（视频片段）、`speech-generator`（TTS配音）
- 凭据：复用项目根目录 `.env` 中的 Ark API 配置

## 剧本创作方法论（内置）
- **黄金三秒**：第一镜必须出钩子，禁止铺垫闲聊
- **角色≤3个**：主角 + 对手/伙伴 + 助攻，每人有记忆点标签
- **外观锁定段**：每个角色写完整外观（年龄/发型/服装/配饰/体态），逐字复制到每个镜头 prompt
- **爆点五段式**：触发→放大→扭转→兑现→余波
- **三类钩子**：悬念钩（清晰问题）、情感钩（共情）、信息钩（信息差）
- **对白驱动哲思**：通过自然对话展现主题，不用旁白说教
- **单镜≤10秒**：seedance 硬上限

## 工作流程

### 步骤0：环境检查
```bash
.venv/bin/python skills/drama-video-creator/scripts/drama.py doctor
```
检查 .env 凭据、ffmpeg、依赖包。

### 步骤1：新建项目（创意 → 剧本 + 角色）
```bash
.venv/bin/python skills/drama-video-creator/scripts/drama.py new "创意描述" [--shots 7] [--ratio 16:9] [--resolution 1080p] [--style gufeng]
```
- 调用 LLM 生成结构化剧本（题材/梗概/角色/分镜大纲/完整剧本）
- 自动生成每个角色的 CG 风格参考图（用 image-generator，规避真人隐私检测）
- 为每个角色匹配合适的 TTS 音色
- 项目目录：`outputs/drama_video/<project_id>/`

### 步骤2：生成对白配音
```bash
.venv/bin/python skills/drama-video-creator/scripts/drama.py voices <project_id>
```
- 根据分镜台词，为每个角色调用 speech-generator 生成配音 mp3
- 获取每段配音的精确时长，用于后续视频生成时的时间规划

### 步骤3：生成视频片段
```bash
.venv/bin/python skills/drama-video-creator/scripts/drama.py gen <project_id>
```
- 每个分镜的 prompt 构建：`[风格锚点] + [角色外观锁定段逐字复制] + [场景] + [人物动作表情+对白对应表演] + [运镜]`
- 逐个调用 video-generator 生成10秒片段（传角色参考图）
- 已完成的片段自动跳过（断点续跑）

### 步骤4：合成成片
```bash
.venv/bin/python skills/drama-video-creator/scripts/drama.py compose <project_id>
```
- 合成风格化 BGM（对白段落自动 ducking 降音）
- 按时间线精确放置对白音轨（给画面铺垫2-3秒再放对白）
- ffmpeg xfade 交叉淡入淡出拼接视频
- 生成片头片尾字幕卡片
- 输出最终成片 final.mp4

### 一键完成
```bash
.venv/bin/python skills/drama-video-creator/scripts/drama.py run "创意描述" [选项]
```
自动执行 new → voices → gen → compose 全流程。

### 单片段重生成
```bash
.venv/bin/python skills/drama-video-creator/scripts/drama.py redo <project_id> <镜头号>
```

## 项目目录结构
```
outputs/drama_video/<project_id>/
├── project.json        # 单一事实源（状态+剧本+分镜+配音+视频路径）
├── script.md           # 人类可读剧本
├── shots.md            # 人类可读分镜表
├── characters/
│   ├── ref_角色1.jpg   # 角色参考图（CG风格）
│   └── ref_角色2.jpg
├── voices/
│   ├── s01_girl.mp3
│   ├── s01_hero.mp3
│   └── ...
├── segments/
│   ├── shot_01.mp4
│   └── ...
└── final.mp4           # 成片
```

## 音色匹配策略
- 男主角：`ICL_zh_male_zhangjianxiake_tob`（仗剑侠客/清朗男声）
- 女主角：`zh_female_gufengshaoyu_mars_bigtts`（古风少御/英气女声）
- 反派/冷峻角色：`ICL_zh_male_gugaogongzi_tob`（孤高公子/冷峻男声）
- 旁白/辅助：`zh_male_jieshuonansheng_mars_bigtts`（磁性解说男声）
- 可根据题材自动匹配（都市→阳光青年、古风→仗剑侠客等）

## 风格锚点模板
- **gufeng（古风武侠）**：国风3D CG动画风格，国漫精品画质，青白水墨色调配暖色光影，电影级运镜
- **urban（现代都市）**：现代都市写实风格，电影质感，自然光影，4K高清画质
- **noir（悬疑暗黑）**：暗色电影质感，低调光影，高对比度，冷色调，悬疑氛围
- **bright（欢快治愈）**：明亮清新色调，暖色系，柔和光影，治愈系画面

## 审核规避要点
- 不使用真人照片作参考图，用 image-generator 生成 CG/插画风格参考图
- 直白打斗词汇（打/杀/攻击/对决）改为"切磋/对峙张力/剑舞交错"
- 血腥/暴力/犯罪场景不直接描写，改为氛围暗示
- 如有 PolicyViolation 错误，自动修改 prompt 重试（最多2次）

## 注意事项
1. 视频生成单段10s/1080p约需4-5分钟，全流程7段约30-40分钟
2. 角色参考图必须是CG/插画/3D风格，不能是真人照片
3. 对白是先于视频生成的（确定时长后再让视频按表演生成），保证音画同步
4. BGM在对白段落自动降低至30%音量，非对白段落45%
5. 每个镜头prompt必须包含角色完整外观段（逐字复制，禁止同义改写），这是防人物漂移的关键
