---
name: svg-diagram-verification
description: "Verify SVG diagrams via DOM geometry when vision fails."
---

# SVG 架构图渲染验证（视觉验证降级方案）

生成 SVG-as-HTML 架构图后（如 architecture-diagram 技能产物），首选
browser_vision 目视验证；当视觉分析不可用时，用 DOM 几何断言兜底。

## 触发条件
- 需要验证 SVG 图表渲染质量，但 browser_vision / vision_analyze 连续超时
- vision 截图拍到空白页（navigate 后立即截图的渲染延迟）
- 想批量/程序化检查多张图的坐标级缺陷

## 验证流程
1. `browser_navigate` 打开图（file:// URL 即可）
2. `browser_console` 执行 `scripts/svg_geom_check.js`（整段粘进 expression）
3. 检查三类缺陷：
   - **越界**：rect 的 x+w / y+h 超出 viewBox
   - **重叠**：两 rect 相交（自动跳过同坐标双 rect——architecture-diagram 的
     遮罩技法会成对出现同几何矩形，属预期）
   - **文字越界**：text 的 x 坐标超出画布
4. 返回 `{outOfCanvas, overlaps, textOutOfRange}`，全空即通过；
   有缺陷 → patch 坐标 → 重新验证

## 局限（重要）
浏览器 DOM 检查（JS 脚本）查不出：箭头穿过盒子后悬空的视觉瑕疵、配色/对齐的
美观问题——这些仍需 vision 或目视。但坐标级缺陷能可靠抓到（实测案例：一条
箭头 path 终点穿过目标盒子 300px 导致箭头悬空，DOM 检查发现坐标异常后修复）。
「文字软溢出」DOM JS 版只能查 text 是否出画布、查不出「文字超盒子宽度」——
这个缺口由下方 Python 版补齐（CJK 宽度感知估算）。

## 无浏览器 / 无 vision 时的降级：Python 直接解析 SVG

当 browser_* 工具与 vision 同时不可用（如 browser-harness daemon 起不来 +
模型报 "do not support image input"）时，不依赖浏览器也能做坐标级验证：

1. 用 Python `xml.etree` 直接从 HTML 里抽出 `<svg>…</svg>`（`<svg>` 已带
   xmlns，**别再手动注入**，否则 duplicate attribute 报错），`ET.fromstring` 解析。
2. 遍历 rect/text，检查越界（rect 的 x+w/y+h、text 的估算左右边界是否超 viewBox）。
3. **文字软溢出**：按等宽字体估文字宽——CJK 字符 `unicodedata.east_asian_width`
   为 W/F 算 1em，其余（ASCII）约 0.62em（JetBrains Mono）。`text-anchor="middle"`
   的文字左边界 = x − width/2，对照容器框宽即可发现「文字超出盒子宽度」。
4. 渲染冒烟：Chrome headless 截图兜底，浏览器 daemon 挂了也能用——
   `"/Applications/Google Chrome.app/.../Google Chrome" --headless --disable-gpu
   --screenshot=/tmp/x.png --window-size=1240,1080 file://…`，截图非空即渲染成功。
   vision 不可用时无法「看」截图，所以截图只作「非空 = 渲染成功」的冒烟，
   精细缺陷仍靠第 3 步的程序化坐标检查。

可复用脚本：`scripts/svg_geom_check.py`（`python3 svg_geom_check.py <file.html> [containers.json]`）。

## vision 拍空白的坑
navigate 后立即 screenshot 可能拍到空白；vision 报"空白画面"时：先稍等再截、
或对已保存的 screenshot 文件用 vision_analyze 重试；两者都失败就转 DOM 检查，
不要反复烧 vision 重试。

## vision 不可用时的美观前置收敛（关键）

坐标校验抓不住「丑」——它只能发现越界/溢出，抓不到配色花哨、嵌套过深、
小字太密这些用户一眼就反感的问题。当 vision 不可用时，**画图前就要收敛美观**，
不要画完再靠坐标校验补救（那时已经晚了）。

收敛原则（本会话实证：一张图用了 7 色 + 4 层嵌套 + 9px 小字，被用户判「改丑了」）：
- **颜色 ≤ 4 种**：语义色板有 7+ 色，但单图不要全上。收敛到「层级主色 + 边界色 +
  箭头色 + 中性灰」即可；多色混排 = 花哨凌乱。
- **嵌套 ≤ 2 层**：大框套小框再套更小框（>2 层）必然视觉混乱。优先用「平铺 + 箭头」
  表达层级关系，而非层层嵌套矩形。
- **字号 ≥ 10px**：中文内容尤其。architecture-diagram 色板的 9/8/7px 只适合英文
  short label，中文下会挤成一团；加大字号 + 留白。
- **留白充足**：框间距、行距宁可大不要小。

重画一次通常比反复微调坐标更快更有效——直接按收敛原则重写，别在丑图上缝缝补补。
