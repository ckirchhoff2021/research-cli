---
name: speech-generator
description: 专业语音生成技能，支持语音克隆、跨语言合成、指令遵循生成三种能力，内置在线+离线双合成方案。当用户要求生成语音、语音复刻、指定音色生成音频、跨语言/方言语音合成、按指令（如指定语言、语气、语速）生成语音时必须使用此技能，即使没有明确提及语音生成也要触发。
---

# speech-generator 语音生成技能
## 核心能力
### 双方案策略
1. **优先在线合成方案**：适用于常规语音合成需求，内置数百款预制音色，无需本地部署环境即可快速生成
2. **离线合成方案（CosyVoice）**：适用于语音克隆、自定义指令生成等个性化需求，需要本地部署CosyVoice环境
> 方案选择逻辑：
> - 普通语音合成需求 → 优先使用在线方案
> - 用户需要语音克隆/音色复刻、指定特殊生成指令（语气/语速/方言高度定制）→ 使用离线方案
> - 检测到无离线CosyVoice环境时，自动提示用户当前无法进行离线生成，引导使用在线方案

### 能力列表
1. **常规语音合成**：离线(voice_clone)和在线方案均支持，根据用户需要的音色特点，匹配内置的音色进行语音合成
2. **语音克隆（voice_clone）**：仅离线方案支持，根据参考音频复刻音色，生成相同音色的语音
3. **跨语言合成（cross_lingual_gen）**：双方案均支持，生成指定方言/语言的语音，支持中文方言（四川话、粤语、东北话等）和多语种
4. **指令遵循生成（instruct_gen）**：双方案均支持，根据自然语言指令生成语音，支持指定语言、语气、语速等要求

## 使用前提
### 在线方案
- 无需额外环境部署，直接调用接口生成，支持音色列表参考[voice_list.json](./assets/voice_list.json)
### 离线方案
- 已部署CosyVoice项目，路径：/home/chenxiang.101/workspace/CosyVoice
- 参考音频（音色）可提供自定义路径，也可使用内置支持的音色，支持音色列表详情可参考[timbre.json](./assets/timbre.json)

## 使用步骤
1. **方案选择判断**：
   - 若用户需求为语音克隆/音色复刻 → 走离线方案
   - 若用户仅常规语音合成（指定音色、文本）→ 走在线方案
   - 若用户有特殊定制化生成要求（语气/语速/方言高度自定义）→ 走离线方案
   - 调用离线方案前先检测CosyVoice环境是否存在，不存在时提示用户：`当前检测到未部署离线CosyVoice环境，无法进行[语音克隆/定制化生成]，请使用在线语音合成方案，支持数百款预制音色选择。`
2. 确定生成类型：常规语音合成/语音克隆/跨语言合成/指令遵循生成
3. 提取用户输入的合成文本、参考音频路径（离线用）、音色类型（在线用）、生成指令（可选）
4. 调用对应封装脚本执行合成任务
5. 返回生成音频的下载链接和预览窗口给用户

## 输入参数
### 通用参数
| 参数名 | 类型 | 是否必填 | 说明 |
|--------|------|----------|------|
| tts_text | string | 二选一 | 需要合成的文本内容（适合短文本，长度建议<2000字） |
| tts_file | string | 二选一 | 包含待合成内容的文本文件路径（适合长文本，避免超时/参数过长问题） |
| output_file | string | 否 | 自定义输出文件路径，默认：outputs/output.wav |

### 在线方案专属参数
| 参数名 | 类型 | 是否必填 | 说明 |
|--------|------|----------|------|
| voice_type | string | 是 | 在线音色ID，参考[voice_list.json](./assets/voice_list.json)选择 |
| background | boolean | 否 | 是否后台执行（默认为false），长文本生成时开启可避免超时问题，生成完成后自动保存到输出路径 |

### 离线方案专属参数
| 参数名 | 类型 | 是否必填 | 说明 |
|--------|------|----------|------|
| task_type | string | 是 | 生成类型：`voice_clone`/`cross_lingual_gen`/`instruct_gen` |
| prompt_wav | string | 否 | 参考音频路径，默认：./asset/zero_shot_prompt.wav |
| instruct_prompt | string | 否 | 生成指令，仅指令遵循生成时必填，例如"用粤语生成"、"用温柔的女声生成" |
| background | boolean | 否 | 是否后台执行（默认为false），长文本生成时开启可避免超时问题，生成完成后自动保存到输出路径 |

- 注意：当用户没有制定输出文件路径时，将文件存储在[YOUR_SKILLS_DIR]/speech-generator/outputs/目录下


## 输出格式
```
✅ 语音生成成功，生成音频已可下载：
[音频名称.wav](sandbox:生成文件绝对路径)
* 合成文本：[你的合成文本]
* 任务类型：[语音克隆/跨语言合成/指令遵循生成]
* [可选]参考音频：[参考音频路径]
* [可选]生成指令：[用户指定的生成指令]
```

## 示例
### 示例1：在线方案-常规语音合成
用户请求："用慵懒大叔的音色生成语音：今天周五，马上放假了，真不错，一会儿下班就去吃饭游泳，放松一下"
执行命令：
```
.venv/bin/python [YOUR_SKILLS_DIR]/speech-generator/scripts/tts.py \
  --tts_text "今天周五，马上放假了，真不错，一会儿下班就去吃饭游泳，放松一下" \
  --voice_type zh_male_yuanboxiaoshu_moon_bigtts \
  --output_file "lazy_uncle_demo.mp3"
```

### 示例2：离线方案-语音克隆
用户请求："用我提供的这个音频的音色，生成一段'欢迎来到人工智能世界'的语音"
执行命令：
```
.venv/bin/python [YOUR_SKILLS_DIR]/speech-generator/scripts/generator.py \
  --task_type voice_clone \
  --tts_text "欢迎来到人工智能世界" \
  --prompt_wav "/user/upload/reference.wav"
  --output_file "welcome.wav"
```
### 示例3：离线方案-跨语言合成
用户请求："使用男性深夜播客的音色，用四川话念一段绕口令：八百标兵奔北坡"
执行命令：
```
.venv/bin/python [YOUR_SKILLS_DIR]/speech-generator/scripts/generator.py \
  --task_type cross_lingual_gen \
  --tts_text "[四川话]八百标兵奔北坡，北坡炮兵并排跑，炮兵怕把标兵碰，标兵怕碰炮兵炮" \
  --prompt_wav "[COSYVOICE_PATH]/asset/wavs/zh_male_shenyeboke_emo_v2_mars_bigtts-1.wav"
```
### 示例4：离线方案-指令遵循生成
用户请求："用粤语生成这句话：今天真是个好日子"
执行命令：
```
.venv/bin/python [YOUR_SKILLS_DIR]/speech-generator/scripts/generator.py \
  --task_type instruct_gen \
  --tts_text "今天真是个好日子" \
  --instruct_prompt "用粤语生成"
```

### 示例5：长文本/散文生成（避免超时，双方案通用）
用户请求："把这篇1000字的散文合成磁性男声语音"
执行步骤：
1. 先将文本保存到本地文件：/tmp/speech_content.txt
2. 在线方案执行：
```
.venv/bin/python [YOUR_SKILLS_DIR]/speech-generator/scripts/tts.py \
  --tts_file "/tmp/speech_content.txt" \
  --voice_type zh_male_audiobook \
  --background true \
  --output_file "prose_recitation.mp3"
```
3. 离线方案执行：
```
.venv/bin/python [YOUR_SKILLS_DIR]/speech-generator/scripts/generator.py \
  --task_type instruct_gen \
  --tts_file "/tmp/speech_content.txt" \
  --instruct_prompt "用有磁性的男声生成，语速适中" \
  --background true \
  --output_file "prose_recitation.wav"
```
生成完成后可以直接返回输出文件路径给用户。

## 最佳实践
- 文本长度超过2000字时，必须使用`--tts_file`参数传入文本，不要直接用`--tts_text`避免命令行参数过长报错
- 文本长度超过500字时，建议开启`--background true`后台执行，避免生成时间过长导致超时
- 后台执行时生成日志保存在CosyVoice目录下的generation.log文件，可用于排查问题
