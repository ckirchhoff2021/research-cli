---
name: video-generator
description: 专业视频生成技能，支持文本生成视频、图文转视频、带背景音乐/参考视频的定制化视频生成。当用户要求生成视频、制作宣传片、图文转视频、根据脚本生成视频时触发此技能。支持自定义时长、画面比例、背景音乐、参考视频风格、首帧/尾帧图片等参数。
---

# 视频生成技能使用指南

## 功能说明
本技能封装了本地视频生成模型调用能力，支持：
1. 文本prompt直接生成视频
2. 参考图片+文本描述生成连贯视频
3. 参考视频风格+文本描述生成视频
4. 自定义背景音乐、字幕、分镜脚本生成视频
5. 支持指定视频时长、宽高比、分辨率
6. 海报批量生成视频：`scripts/batch.py`，按组轮转风格批量出片（`make`），内容审核拦截时自动换风格补齐（`fill`）

## 触发场景
当用户有以下需求时必须使用本技能：
- 要求生成任何类型的视频内容
- 需要制作宣传广告、短视频、剧情片等视频
- 需要将图文内容转换为视频
- 需要基于已有图片/视频生成新的视频
- 需要为视频添加背景音乐、配音、字幕等

## 使用流程

### 1. 收集必要参数
向用户确认以下参数，如果用户未提供则使用默认值：
| 参数名 | 说明 | 示例 | 默认值 | 必填 |
|--------|------|------|--------|------|
| prompt | 视频内容描述，越详细越好 | "第一人称视角果茶宣传广告，seedance牌「苹苹安安」苹果果茶限定款..." | - | 是 |
| images | 参考图片路径/URL列表，逗号分隔 | "https://xxx/pic1.jpg,/home/xxx/pic2.jpg" | 空 | 否 |
| videos | 参考视频路径/URL列表，逗号分隔 | "https://xxx/video1.mp4" | 空 | 否 |
| audios | 背景音乐/配音路径/URL列表，逗号分隔 | "https://xxx/audio1.mp3" | 空 | 否 |
| ratio | 视频宽高比 | "16:9", "9:16", "4:3" | "16:9" | 否 |
| duration | 视频时长，单位秒 | 11 | 10 | 否 |

### 2. 执行视频生成任务
在后台执行视频生成命令，格式如下：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/video-generator/scripts/generator.py --prompt "视频内容描述" [--images 图片列表] [--videos 参考视频列表] [--audios 音频列表] [--ratio 宽高比] [--duration 时长]
```

### 3. 任务管理
- 立即返回给用户任务启动确认，包含进程ID、日志路径、预计执行时间
- 任务执行完成后第一时间通知用户，提供本地视频路径和临时预览链接
- 如果临时链接过期，直接提供本地文件下载
- 支持用户随时查询任务进度

### 4. 结果返回
任务完成后返回以下信息：
✅ 视频生成任务已执行成功！
- 在线观看链接：<临时链接>
- 本地保存路径：<绝对路径>

## 示例

### 输入
用户请求："帮我生成一个果茶宣传广告视频，首帧是苹果图片，尾帧是果茶成品图，用指定的背景音乐和参考视频风格，时长11秒，16:9比例"

### 执行命令
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/video-generator/scripts/generator.py --prompt "全程使用视频1的第一视角构图，全程使用音频1作为背景音乐。第一人称视角果茶宣传广告，seedance牌「苹苹安安」苹果果茶限定款；首帧为图片1，你的手摘下一颗带晨露的阿克苏红苹果，轻脆的苹果碰撞声；2-4 秒：快速切镜，你的手将苹果块投入雪克杯，加入冰块与茶底，用力摇晃，冰块碰撞声与摇晃声卡点轻快鼓点，背景音：「鲜切现摇」；4-6 秒：第一人称成品特写，分层果茶倒入透明杯，你的手轻挤奶盖在顶部铺展，在杯身贴上粉红包标，镜头拉近看奶盖与果茶的分层纹理；6-8 秒：第一人称手持举杯，你将图片2中的果茶举到镜头前（模拟递到观众面前的视角），杯身标签清晰可见，背景音「来一口鲜爽」，尾帧定格为图片2。背景声音统一为女生音色。" --images https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic1.jpg,https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic2.jpg --videos https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_tea_video1.mp4 --audios https://ark-project.tos-cn-beijing.volces.com/doc_audio/r2v_tea_audio1.mp3 --ratio 16:9 --duration 11
```

### 返回用户
✅ 果茶宣传广告视频生成任务已在后台启动：
- 进程ID：3852993
- 运行日志路径：/tmp/tea_ad_video_gen.log
- 预计执行时间：15-25分钟

任务执行完成后我会第一时间将生成的视频结果推送给你，你也可以随时询问进度。

## 批量生成：batch.py

当用户要求「用一整目录的海报批量出短视频」「每组出 N 个不同风格的视频」时，用
`scripts/batch.py` 而不是手写循环。海报按子目录分组（每组一个人物/主题），
输出 `<out-dir>/<组名>/<序号>_<风格>.mp4`。海报文件需以 `_<风格slug>` 结尾
（如 `01_pixar3d.jpg`，与 image-generator 的 `batch.py` 产物天然对应）。

### make：每组批量出 N 个

跨组轮转风格窗口（组 0 取第 1–N 个风格，组 1 取第 N+1–2N 个……），保证所有风格被覆盖：

```bash
.venv/bin/python [YOUR_SKILLS_DIR]/video-generator/scripts/batch.py make \
  --posters-dir "outputs/my_task/posters" --out-dir "outputs/my_task/videos" \
  --videos-per-group 5 --workers 4

# 参数自检：只打印计划，不调用接口
... batch.py make --posters-dir ... --out-dir ... --dry-run
```

### fill：为不足 N 个的组补齐

按优先级（默认先卡通插画类、后真人/版权风险类）逐个尝试候选风格，
被内容审核拦截（Sensitive/copyright/400）立即换下一个，直到每组凑满 N 个：

```bash
.venv/bin/python [YOUR_SKILLS_DIR]/video-generator/scripts/batch.py fill \
  --posters-dir "outputs/my_task/posters" --out-dir "outputs/my_task/videos" \
  --target 5
```

公共参数（两个子命令通用，写在子命令之后）：

| 参数 | 说明 | 默认 |
|---|---|---|
| `--posters-dir` / `--out-dir` | 海报目录（每组一个子目录）/ 视频输出目录，必填 | 必填 |
| `--motion-file` | JSON 文件新增/覆盖风格动作：`{"slug": "动作文本"}` | 内置 30 种 |
| `--prompt-template` | 提示词模板，占位符 `{motion}` | 内置模板 |
| `--ratio` / `--duration` / `--resolution` | 画幅 / 秒数 / 清晰度 | `9:16` / 5 / `720p` |
| `--workers` / `--timeout-s` | 并发数 / 单任务轮询上限秒数 | 4 / 1200 |
| `--skip-dirs` | 海报目录下忽略的子目录 | `_converted,_resized,_sheets,_gallery,_cache` |
| `--dry-run` | 只打印计划不调用接口 | 否 |

make 专有：`--videos-per-group`（默认 5）；fill 专有：`--target`（默认 5）、
`--priority-file`（JSON 数组，风格 slug 的补齐顺序）。

注意：
- 断点续跑：已存在且大于 100KB 的视频自动跳过，失败任务写入 `<out-dir>/failures.json`；
- 风格 slug 与动作库同构于 image-generator 的 30 种风格，新增风格用 `--motion-file`，
  不要把业务路径硬编码进脚本；
- 真人写实海报易被视频侧 400 拦截，优先用卡通/插画化海报，拦截后用 `fill` 补齐。

## 场景剧批量：scenes 子命令（同一角色 × 多场景 × 带台词）

当用户要「用同一张角色图生成多个有剧情、有台词的场景短视频」时，用 `scenes` 子命令 +
场景预设，**不要手写循环脚本**。预设位于 `presets/<name>.json`：

```bash
.venv/bin/python skills/video-generator/scripts/batch.py scenes \
  --scenes-file adventure-scenes \
  --ref-image outputs/任务/refs/角色.jpg \
  --out-dir outputs/任务/clips \
  --duration 8 --ratio 16:9 --resolution 720p --workers 4
```

- 内置预设 `adventure-scenes`：30 集（旅游 / 骑马 / 轻功水上漂 / 开飞机 / 写代码，各 6 集），
  每集含完整分镜、中文台词、环境音/BGM 提示，自动开启配音。
- 只生成部分：`--themes 01_环游世界` 或 `--themes shibuya,captain`；试跑用 `--limit 1`。
- 输出 `<out-dir>/<主题>/<序号>_<slug>.mp4`，并生成 `scenes_manifest.json` 供合成使用。
- 新增成套场景：往 `presets/` 加 JSON（`prompt_prefix` + `items[{theme,slug,title,duration?,prompt}]`），
  也支持直接传 JSON 路径。断点续跑规则同 make/fill。

## 长视频合成：scripts/concat.py

把 scenes（或任意目录）的短视频统一规格（分辨率/帧率/像素格式/音频）后拼接为长视频，
自动生成片头、章节卡、集名卡、片尾；系统 ffmpeg 损坏时自动改用 imageio-ffmpeg 内置静态版；
无音轨的片段自动补静音：

```bash
.venv/bin/python skills/video-generator/scripts/concat.py \
  --manifest outputs/任务/clips/scenes_manifest.json \
  --output outputs/任务/阿哲的奇妙冒险_长片.mp4 \
  --title "阿哲的奇妙冒险" --cards
```

没有 manifest 时可 `--clips-dir <目录>`（递归收集 mp4）。参数：`--card-duration`、
`--intro/outro-duration`、`--width/--height/--fps`、`--reencode-final`（最终阶段也重编码，更稳更慢）。

## ⚠️ 长片故事性规范（story 优先，不要平行罗列场景）

当用户要的是**长片/有故事性**的视频，**禁止**把同一主题的 N 个场景平行罗列（"旅游6集、骑马6集"
彼此无因果 = 场景集锦，不是故事）。必须用故事预设（如 `adventure-story`），并满足：

1. **一个目标**：主角有非达成不可、且有期限的具体目标；
2. **因果链**：相邻场景必须是"因为上一集……所以本集……但是……"，每集开头写明前情、结尾交钩子；
3. **阻碍与代价**：目标越来越难，主角要付出代价（恐惧、受伤、想放弃）；
4. **角色弧光**：主角开场与结尾必须发生改变；
5. **连续性**：固定道具/伙伴/配角贯穿（如怀表、逐张明信片、小圆），三幕结构清晰
   （建置→对抗→高潮→解决），中点与"灵魂黑夜"要有；
6. 用 `preset_to_screenplay.py` 先导出剧本给用户确认，再批量生成 + `concat.py --cards` 合成。

故事预设参考 `presets/adventure-story.json`（30集：序章来信3 / 循迹世界6 / 策马追风6 /
渡水而行6 / 学会飞翔6 / 极光归途3）。
