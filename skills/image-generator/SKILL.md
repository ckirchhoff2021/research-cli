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
5. 自动保存：所有生成的图像自动保存到outputs目录

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
