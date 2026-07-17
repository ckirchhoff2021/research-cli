---
name: image-generator
description: 生成图像、图像风格转换的专业技能，支持文本生成图像、基于已有图像转换风格、自定义输出尺寸。当用户要求生成图像、AI画图、图像风格转换、图片处理时触发此技能。
---

# Image Generator Skill

专业的图像生成与风格转换技能，支持文本生成图像和基于现有图像的风格转换，自动保存输出结果到指定目录。

## 核心功能
1. 文本生成图像：根据用户提示词生成指定风格的图像
2. 图像风格转换：基于现有图像转换为目标风格
3. 自定义尺寸：支持指定输出图像分辨率（如"2K", "4K", "1024x768"等）
4. 自动保存：所有生成的图像自动保存到outputs目录

## 工作流程

### 1. 文本生成图像
当用户提供文本提示词要求生成图像时：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "<用户提供的提示词>" [--size "<自定义尺寸>"]
```
- 自动保存生成的图像到outputs目录，文件名格式：`{style}_{subject}.jpg`
- 返回给用户：预览链接 + 本地保存路径

### 2. 图像风格转换
当用户提供原始图像路径，要求转换风格时：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "<风格转换提示词>" --image "<用户提供的原始图像路径>" [--size "<自定义尺寸>"]
```
- 自动保存生成的图像到outputs目录，文件名格式：`{new_style}_{original_filename}.jpg`
- 返回给用户：预览链接 + 本地保存路径

## 输入参数说明
| 参数 | 必选 | 说明 |
|------|------|------|
| prompt | 是 | 图像描述/风格描述提示词 |
| image | 否 | 原始图像路径，用于风格转换场景 |
| size | 否 | 输出图像尺寸，默认使用模型默认尺寸 |

## 输出要求
每次生成完成后必须同时返回：
1. 图像预览链接（可直接查看）
2. 本地保存的绝对路径

## 示例
### 示例1：文本生成图像
**用户输入**：生成一张宫崎骏风格的中年男人形象
**执行命令**：
```bash
python -m tests.dream.generator --prompt "生成一张宫崎骏风格的中年男人形象"
```
**输出**：
> 生成完成，宫崎骏风格中年男人形象图片链接：
> ![宫崎骏风格中年男人](<预览链接>)
> 本地保存路径：`outputs/ghibli_middle_age_man.jpg`

### 示例2：图像风格转换
**用户输入**：帮我把这张图像转换成草图风格，尺寸2K，原始路径是/home/chenxiang.101/workspace/tmp/yemen.jpg
**执行命令**：
```bash
python -m tests.dream.generator --prompt "帮我把这张图像转换成草图风格" --image /home/chenxiang.101/workspace/tmp/yemen.jpg --size "2K"
```
**输出**：
> 已完成图像风格转换，生成的草图风格2K图像：
> - 预览链接：![草图风格图像](<预览链接>)
> - 本地保存路径：`outputs/sketch_style_yemen.jpg`
