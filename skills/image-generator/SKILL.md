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
**用户输入**：帮我把这张图像转换成草图风格，尺寸2K，原始路径是 /path/to/input.jpg
**执行命令**：
```bash
.venv/bin/python [YOUR_SKILLS_DIR]/image-generator/scripts/generator.py --prompt "帮我把这张图像转换成草图风格" --image "/path/to/input.jpg" --size "2K"
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

### 预设模式：--preset（成长时间线等成套提示词，禁止再手写循环脚本）

当需求是一套**固定成套**的生成（如「同一个人 5→80 岁的成长海报」），直接用技能内置预设，
不要再写一次性 Python 脚本。预设位于 `presets/<name>.json`，自带成套描述与提示词模板：

```bash
# 内置预设 aging-pixar：5~80 岁每 5 岁一张皮克斯成长海报（40 岁起带小胡子并随年龄渐白）
.venv/bin/python skills/image-generator/scripts/batch.py \
  --preset aging-pixar \
  --refs-dir "outputs/我的任务/refs" \
  --out-dir "outputs/我的任务/images" --workers 4

# 只要其中几个年龄（slug 子集）
... batch.py --preset aging-pixar --styles age05,age35,age80 ...

# 也可传自定义预设 JSON 的绝对路径
... batch.py --preset /path/to/my_preset.json ...
```

预设文件格式（以后遇到成套需求，优先往 `presets/` 加文件）：

```json
{
  "prompt_template": "...{style_name}...{transform}...",
  "items": [
    {"slug": "age05", "name": "5岁", "filename": "05岁.jpg", "transform": "年龄外观+场景的完整描述"}
  ]
}
```

当前内置预设：
- `aging-pixar`：16 张成长时间线（5→80 岁，40 岁起带小胡子）
- `business-attire`：10 张职业白领正装照（经典西装/三件套/礼服/商务休闲/路演/科技风/新中式/差旅等）
- `id-photo`：20 张证件照（服装×底色×表情，Seedream 直出纯色底）
- `photo-restore`：旧的单图修复预设（批量场景备用）；单张照片修复请直接用下面的 `portrait_polish.py`
- `ceo-poster`：20 张霸道总裁主题海报（高尔夫/休闲/穿衣穿袜/健身/游泳/穿鞋/内衣大片/商务/马术）

### 联系表：contact_sheet.py

批量生成后用通用拼图工具一键出总览（不要再手写拼图脚本）：

```bash
.venv/bin/python skills/image-generator/scripts/contact_sheet.py \
  --images-dir "outputs/我的任务/images/<参考图名>" \
  --output "outputs/我的任务/contact_sheet.jpg" --cols 5
```

常用参数：`--pattern`（默认 `*.jpg`）、`--recursive`、`--cols`、`--cell-w/--cell-h`、
`--label auto|none`、`--font-size`；按文件名数字自然排序，自动跳过 contact/sheet 类图。

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

## 证件照：Seedream 直出（不要抠图换底）

用户要证件照/档案照时，**直接让 Seedream 分别生成白/蓝/红底三张原片**，再按比例缩放成
一寸(295×413)/二寸(413×579)、写 300dpi；**不要做蓝幕抠图换底**（发丝/眼镜边缘会出瑕疵）。
提示词要点：与参考图同一人、正面免冠、双耳露出、双眼平视、中性表情、有领正装、
均匀正面光、指定纯色无缝背景布、写实摄影（严禁卡通）、竖版 5:7、无边框无文字。
2K 出图通常为 1760×2464（即 5:7），与一寸/二寸同比例，仅缩放不裁切。

### 证件照预设：id-photo + 打印尺寸导出

成套证件照用预设（Seedream 直出、不抠图），再用 `resize.py` 批量出打印尺寸：

```bash
# 20 个「服装×底色×表情」组合，2K 原片（1760×2464 = 5:7）
.venv/bin/python skills/image-generator/scripts/batch.py --preset id-photo \
  --refs-dir outputs/.../refs --out-dir outputs/.../原片2K --workers 4
# 原片 -> 一寸(295×413)/二寸(413×579)，300dpi
.venv/bin/python skills/image-generator/scripts/resize.py \
  --images-dir outputs/.../原片2K/阿哲 --out-dir outputs/.../打印版 \
  --specs 一寸,二寸 --dpi 300
```

`resize.py` 支持 `一寸/小一寸/大一寸/二寸/小二寸`；等比适配、边缘色补边不拉伸。
注意：提示词描述底色用中文（如"浅灰色背景布"），**不要写 #十六进制色号**，
模型可能把色号当文字渲染进画面；可加"画面中不要出现任何数字、字母或文字"。

## 纯提清晰度：superres.py（不改五官 / 不美颜 / 不重绘）

用户只说「提高清晰度 / 修复模糊，不要动五官」时，**必须用确定性超分，不要用 Seedream**
（生成式重绘即使构图锁定，仍可能轻微改动五官或肤质）。`scripts/superres.py` 用
Real-ESRGAN 的 CoreML 卷积网络逐块超分，几何身份逐像素保持：

```bash
.venv/bin/python skills/image-generator/scripts/superres.py \
  --image outputs/.../photo.jpg --out-dir outputs/.../超分
# 固定 512 tile、64 overlap 羽化加权，输出 _超分4x.jpg（6912x9216）+ _超分_原尺寸.jpg
# 以拉普拉斯方差量化清晰度（实测 7.25 -> 64.0）；--usm 控制附加锐化，--compute-unit 选加速单元
```

模型文件 `models/coreml/RealESRGAN.mlmodel`（首次运行若换模型重新放入即可）。

## 人像精修：portrait_polish.py（允许自然美颜 / 生成式重绘，强制零裁剪）

用户说「照片模糊、提升清晰度、修复面部、美化一下、毛孔太明显」时，一律用本工具，
不要再手写提示词或临时脚本：

```bash
# 高清修复 + 轻度自然美颜（默认）：收敛毛孔、淡化痘印斑点、均匀肤色，但保留真实纹理
.venv/bin/python skills/image-generator/scripts/portrait_polish.py \
  --image outputs/.../photo.jpg --mode beautify --size 4K

# 只去模糊、不改肤质
... portrait_polish.py --image ... --mode restore

# 批量纯直出（用户怀疑合成/形变时）：跑 N 次整图生成，原样保留构图达标的成图，
# 不做相似变换、不做合成；自动出带偏差标注的候选总览，挑形变最小的
.venv/bin/python skills/image-generator/scripts/portrait_polish.py \
  --image outputs/.../photo.jpg --collect 12 --tolerance 0.05
```

机制（都已内置，无需人工介入）：
- **白边预补偿**：Seedream 图生图几乎总会把人物放大约 1.5~3 倍（就是用户看到的"被裁剪"）。
  工具先把原图居中放到约 3 倍大、同背景色的画布上（自动取边缘色），模型再放大时净效果
  正好回到原构图；白边倍数随每轮构图偏差自适应（受接口 36MP 上限封顶）。
- **构图校验**：用 res10 SSD 人脸框 + 眼镜专用 Haar 级联定位双眼，量化人物缩放与位移，
  偏差 >3% 自动重跑；成图再用相似变换按双眼对齐到原构图，任何分辨率下取景与原片逐边一致。
- **合成兜底**：模型连续抖动、整图无法达标时，把美颜脸部对齐后羽化合成回增强原片，
  保证任何情况下都零裁剪、无黑边。

产物：`<out-dir>/<名>_自然精修_原尺寸.jpg`（可直接替换原图）、
`<名>_自然精修_4K.jpg`、`_对比_*.jpg`。交付前必须目检对比图：
只允许"更清晰 + 肤质更细腻"，身份、表情、构图有任何变化就重跑。
