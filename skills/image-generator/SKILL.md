---
name: image-generator
description: 生成图像、图像风格转换、多图融合的专业技能，支持文本生成图像、基于已有图像转换风格、自定义输出尺寸。当用户要求生成图像、AI画图、图像风格转换、图片处理时触发此技能。
---

# Image Generator Skill

专业的图像生成与风格转换技能，支持文本生成图像、基于现有图像的风格转换，以及多张参考图合成一张新图，自动保存输出结果到指定目录。

## 核心功能
1. 文本生成图像：根据用户提示词生成指定风格的图像
2. 图像风格转换：基于现有图像转换为目标风格
3. 多图融合：支持传入多张参考图，让模型融合主体、风格或构图生成一张新图
4. 自定义尺寸：支持指定输出图像分辨率（如"2K", "4K"）
5. 批量风格迁移：对一整个参考图目录批量生成多种风格海报（`scripts/batch.py`，并发+断点续跑）
6. 自动保存：所有生成的图像自动保存到outputs目录

## 工作流程

### 1. 文本生成图像
当用户提供文本提示词要求生成图像时：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "<用户提供的提示词>" [--size "<自定义尺寸>"]
```
- 自动保存生成的图像到outputs目录，文件名格式：`dream_<毫秒时间戳>.jpg`
- 返回给用户：预览链接 + 本地保存路径

### 2. 图像风格转换
当用户提供原始图像路径，要求转换风格时：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "<风格转换提示词>" --image "<用户提供的原始图像路径>" [--size "<自定义尺寸>"]
```
- 自动保存生成的图像到outputs目录，文件名格式：`dream_<毫秒时间戳>.jpg`
- 返回给用户：预览链接 + 本地保存路径

### 3. 多图融合
当用户提供多张原始图像，希望合成一张新图时：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "<合成提示词>" --image "<图1路径或URL>" --image "<图2路径或URL>" [--image "<图3路径或URL>"] [--size "<自定义尺寸>"]
```
- `--image` 支持重复传入多次
- 也支持逗号分隔写法：`--image "a.jpg,b.jpg,https://example.com/c.jpg"`
- 自动保存生成的图像到outputs目录
- 返回给用户：预览链接 + 本地保存路径

## 输入参数说明
| 参数 | 必选 | 说明 |
|------|------|------|
| prompt | 是 | 图像描述/风格描述提示词 |
| image | 否 | 参考图路径或 URL；支持单张，也支持通过重复 `--image` 或逗号分隔传入多张 |
| size | 否 | 输出图像尺寸，默认 `2K`，支持 `2K` / `3K` / `4K` |

## 输出要求
每次生成完成后必须同时返回：
1. 图像预览链接（可直接查看）
2. 本地保存的绝对路径

## 示例
### 示例1：文本生成图像
**用户输入**：生成一张宫崎骏风格的中年男人形象
**执行命令**：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "生成一张宫崎骏风格的中年男人形象"
```
**输出**：
> 生成完成，宫崎骏风格中年男人形象图片链接：
> ![宫崎骏风格中年男人](<预览链接>)
> 本地保存路径：`outputs/dream_1720000000000.jpg`

### 示例2：图像风格转换
**用户输入**：帮我把这张图像转换成草图风格，尺寸2K，原始路径是/home/chenxiang.101/workspace/tmp/yemen.jpg
**执行命令**：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "帮我把这张图像转换成草图风格" --image "/home/chenxiang.101/workspace/tmp/yemen.jpg" --size "2K"
```
**输出**：
> 已完成图像风格转换，生成的草图风格2K图像：
> - 预览链接：![草图风格图像](<预览链接>)
> - 本地保存路径：`outputs/dream_1720000000001.jpg`

### 示例3：多张图像合成一张图像
**用户输入**：把第一张图里的女孩、第二张图里的红色风衣、第三张图里的雪山背景融合成一张电影感海报，尺寸 4K
**执行命令**：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py \
  --prompt "将第一张图中的女孩作为主角，穿上第二张图中的红色风衣，并置于第三张图的雪山背景中，生成电影感海报" \
  --image "/path/girl.jpg" \
  --image "/path/red-coat.jpg" \
  --image "/path/snow-mountain.jpg" \
  --size "4K"
```
**输出**：
> 已完成多图融合，生成的 4K 海报图像：
> - 预览链接：![多图融合海报](<预览链接>)
> - 本地保存路径：`outputs/dream_1720000000002.jpg`

### 示例4：逗号分隔传入多张参考图
**用户输入**：把这三张参考图混合成一张赛博朋克风格概念图
**执行命令**：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "融合三张参考图的主体与风格，生成一张赛博朋克概念图" --image "/path/a.jpg,/path/b.jpg,https://example.com/c.jpg"
```
**输出**：
> 已完成多图融合生成：
> - 预览链接：![赛博朋克概念图](<预览链接>)
> - 本地保存路径：`outputs/dream_1720000000003.jpg`

## 批量风格迁移：batch.py

当用户要求「对一批照片批量出 N 种风格海报/批量风格迁移」时，用 `scripts/batch.py`
而不是手写循环。每张参考图 × 每种风格生成一张，输出 `<out-dir>/<参考图名>/<序号>_<风格>.jpg`。

```bash
# 全量：目录中每张参考图 × 全部 30 种内置风格
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/batch.py \
  --refs-dir "outputs/my_task/refs" --out-dir "outputs/my_task/posters"

# 只挑 3 种风格、4 并发、先试跑 1 张验证
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/batch.py \
  --refs-dir "outputs/my_task/refs" --out-dir "outputs/my_task/posters" \
  --styles pixar3d,cyberpunk,wuxia --workers 4 --test

# 只打印执行计划，不调用接口（参数自检用）
... batch.py --refs-dir ... --out-dir ... --dry-run
```

参数：

| 参数 | 说明 | 默认 |
|---|---|---|
| `--refs-dir` / `--out-dir` | 参考图目录 / 输出目录，必填 | 必填 |
| `--styles` | 逗号分隔的风格 slug 子集（如 `pixar3d,ghibli`） | 全部内置风格 |
| `--styles-file` | JSON 文件新增/覆盖风格：`{"slug": {"name": "风格名", "transform": "画面描述"}}` | 无 |
| `--prompt-template` | 提示词模板，占位符 `{style_name}`、`{transform}` | 内置海报模板 |
| `--size` | 生成尺寸 | `2K` |
| `--long-edge` | 参考图长边缩放（像素），0 不缩放 | `1536` |
| `--ext` / `--recursive` | 接受的扩展名；是否递归扫描参考目录 | `jpg,jpeg,png,webp` / 否 |
| `--workers` / `--limit-refs` / `--test` | 并发数 / 只取前 N 张 / 只跑第一个任务 | 4 / 0 / 否 |
| `--dry-run` | 只打印计划不调用接口 | 否 |

内置 30 种风格 slug：`pixar3d ghibli cyberpunk vaporwave superhero shonen popart
vintagetravel space wuxia gothic pixel lego papercut ukiyoe newyear swiss disco clay
picturebook noir graffiti baroque chibi steampunk underwater candy rpg disney glitch`。

注意：
- 断点续跑：已存在且大于 20KB 的结果自动跳过，失败任务写入 `<out-dir>/failures.json`；
- `batch.py` 只做批量编排，单次生成能力与 `generator.py` 完全一致；
- 新风格优先用 `--styles-file` 扩展，不要把业务路径硬编码进脚本。
