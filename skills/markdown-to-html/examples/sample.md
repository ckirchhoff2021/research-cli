# Markdown转HTML工具演示文档

这是一个演示文档，用于展示markdown-to-html工具的各种风格效果。本文档包含了常用的Markdown语法元素，可以测试不同风格下的排版效果。

## 二级标题：功能特性

### 三级标题：核心功能
- ✅ 支持标准Markdown语法转换
- ✅ 多种内置风格模板
- ✅ 自动生成目录导航
- ✅ 代码块语法高亮
- ✅ 数学公式支持
- ✅ 响应式设计

### 三级标题：支持的风格
1. 水墨画风格 (ink-wash)
2. 简约现代风格 (modern)
3. 学术论文风格 (academic)
4. 国风宣纸风格 (xuan-paper)
5. 科技极简风格 (tech-minimal)
6. 优雅印刷风格 (elegant)

## 二级标题：元素展示

### 引用块
> 落霞与孤鹜齐飞，秋水共长天一色。
> —— 王勃《滕王阁序》

> 代码是写给人看的，只是顺便能在机器上运行。
> —— Harold Abelson

### 代码块
```python
def markdown_to_html(content, style="modern"):
    """
    将Markdown内容转换为精美HTML
    :param content: Markdown文本内容
    :param style: 风格名称
    :return: HTML字符串
    """
    md = markdown.Markdown(extensions=MD_EXTENSIONS)
    html_content = md.convert(content)
    template = env.get_template(f"{style}.html")
    return template.render(content=html_content, css=get_style_css(style))
```

```javascript
// JavaScript示例
function fibonacci(n) {
    if (n <= 1) return n;
    return fibonacci(n-1) + fibonacci(n-2);
}

console.log(fibonacci(10)); // 输出55
```

### 表格展示
| 风格名称 | 适用场景 | 特点 |
|---------|---------|------|
| 水墨画 | 国风内容、散文、古诗词 | 宣纸纹理、毛笔字体、水墨元素 |
| 现代简约 | 通用文档、技术说明 | 扁平化设计、清晰层级、响应式 |
| 学术论文 | 研究文档、技术报告 | 规范排版、适合打印 |
| 国风宣纸 | 古文、书法作品 | 淡黄底色、古典边框、印章元素 |
| 科技极简 | 技术文档、API说明 | 暗色主题、代码高亮 |
| 优雅印刷 | 散文、随笔、小说 | 衬线字体、舒适排版 |

### 列表示例
#### 无序列表
- 第一项
- 第二项
  - 子项A
  - 子项B
- 第三项

#### 有序列表
1. 第一步：准备Markdown文件
2. 第二步：选择喜欢的风格
3. 第三步：执行转换命令
4. 第四步：打开生成的HTML文件

### 图片展示
*（示例中省略实际图片链接，实际使用时支持本地和网络图片）*

### 行内元素
- **粗体文本**
- *斜体文本*
- ***粗斜体文本***
- `行内代码`
- [链接示例](https://github.com)
- ~~删除线文本~~

### 数学公式
行内公式：$E=mc^2$

块级公式：
$$
\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}
$$

## 二级标题：使用方法

使用非常简单，只需一行命令即可完成转换：

```bash
python scripts/convert.py 输入文件.md -s 风格名称 -o 输出文件.html
```

## 二级标题：总结

这个工具支持多种美观的风格，可以满足不同场景的文档转换需求。输出的HTML是单文件，所有样式都内联，无需额外依赖，可以直接打开或分享。
