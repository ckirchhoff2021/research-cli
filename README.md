# research-cli

一个基于 DeepAgents 框架的科研工作流命令行工具，帮助自动化日常科研任务。

## 架构概览

```
research-cli/
├── app.py                 # Streamlit Web 界面入口
├── main.py                # 命令行入口，接收任务参数调用代理
├── agent.py               # 核心代理初始化逻辑
├── stream.py              # 流式输出逻辑
├── pyproject.toml         # 项目配置与依赖管理
├── uv.lock                # uv 依赖锁定文件
├── .env / .env.example    # 环境变量配置
├── .streamlit/config.toml # Streamlit 配置
├── memory/                # 代理长期记忆存储，包含 AGENTS.md 行为规范
├── skills/                # 自定义技能集，扩展代理专项能力
│   ├── image-generator    # AI图像生成
│   ├── speech-generator   # 语音合成
│   ├── speech-analyze     # 语音分析转写
│   ├── video-generator    # AI视频生成
│   ├── semantic-retrieval # 语义检索
│   ├── skill-creator      # 自定义技能创建
│   ├── skill-optimizer    # 技能优化
│   ├── picture-book-creator # 绘本创作（支持Markdown/HTML交互两种输出，内置水墨国风模板）
│   ├── web-crawler        # 通用网页爬虫
│   └── markdown-to-html   # Markdown/文本转精美HTML，支持6种风格
├── tools/                 # 自定义工具实现，供代理调用
├── sessions/              # 会话数据存储
├── outputs/               # 输出文件存储（图片、音频、视频等）
└── tests/                 # 测试用例
```

### 核心组件

1. **大模型层**：兼容 OpenAI API 协议的大模型后端，支持自定义模型地址、API Key
2. **DeepAgents 框架层**：提供代理编排、记忆管理、技能调度、工具调用、子代理协作能力
3. **业务扩展层**：
   - 自定义工具：对接科研场景需要的各类 API、脚本、数据处理能力
   - 自定义技能：封装科研领域专业工作流
   - 子代理：拆分复杂任务为多代理协作流程
4. **交互层**：命令行入口，接收用户任务 prompt 并输出执行结果

## 快速开始

### 1. 环境准备

- Python >= 3.12
- uv 包管理器（如果没有可以用 `pip install uv` 安装）

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写你的大模型配置：
```env
BRAIN_API_KEY=你的API密钥
BRAIN_API_URL=模型API地址
BRAIN_MODEL_NAME=使用的模型名称
```

### 4. 运行工具

```bash
uv run python main.py --task_prompt "你的科研任务描述"
```

示例：
```bash
uv run python main.py --task_prompt "给我讲个笑话。"
```

## 扩展开发

### 添加自定义工具

在 `tools/custom_tools.py` 中添加新的工具函数，遵循 DeepAgents 工具定义规范即可被代理自动调用。

### 添加自定义技能

在 `skills/` 目录下新建 SKILL.md 文件，按照技能规范编写领域工作流，代理会自动加载并使用。

### 配置代理行为

编辑 `memory/AGENTS.md` 文件，定义代理的角色定位、行为准则、输出规范等。

## 内置技能列表

项目内置10个AIGC与科研场景专项技能，代理可自动识别任务场景调用对应技能：

| 技能名称 | 功能说明 |
|---------|---------|
| image-generator | AI图像生成，支持多种风格、分辨率自定义，可生成插画、海报、科研示意图等 |
| speech-generator | 语音合成，支持多音色、多语速调整，可生成男/女/童声等不同风格语音 |
| speech-analyze | 语音分析与转写，支持音频转文字、语音内容摘要、声纹特征提取等 |
| video-generator | AI视频生成，支持文本转视频、图片转视频，可自定义时长、帧率、风格 |
| semantic-retrieval | 语义检索，支持本地文档、知识库的语义相似度搜索，快速定位相关资料 |
| skill-creator | 自定义技能创建工具，自动生成符合规范的SKILL.md模板，辅助技能开发 |
| skill-optimizer | 技能优化工具，自动分析技能使用效果，优化技能流程、提示词，提升执行准确率 |
| picture-book-creator | 绘本自动生成，支持Markdown静态绘本与交互式翻页HTML绘本两种输出，内置水墨国风、水彩等多种风格模板，可自动生成分镜脚本、配图、排版，输出完整绘本 |
| web-crawler | 通用网页爬虫，支持静态/动态网页爬取、内容提取、去重清洗，可自动绕过反爬机制抓取科研资料、网页内容 |
| markdown-to-html | Markdown/文本转精美HTML工具，支持水墨画、简约现代、学术论文、国风宣纸、科技极简、优雅印刷等6种内置风格，自动生成目录、代码高亮、数学公式，输出单文件HTML可直接分享 |

## 运行模式

| 模式 | 命令 | 说明 |
|------|------|------|
| 普通模式 | `uv run python main.py --task_prompt "..."` | 一次性输出最终结果 |
| 控制台模式 | `uv run python main.py -c --task_prompt "..."` | 树形结构展示执行过程 |
| 流式模式 | `uv run python main.py -c -s --task_prompt "..."` | 实时流式刷新执行过程 |
| Web 界面 | `uv run streamlit run app.py` | 图形化界面，支持多会话管理 |

## 测试用例

### 基础对话

```bash
# 普通模式
uv run python main.py --task_prompt "讲个笑话"

# 流式模式
uv run python -m tests.test_stream --task "讲个笑话"
```

### 文件操作

```bash
# 读取并分析文件
uv run python -m tests.test_stream --task "读取 main.py 的内容并告诉我它是做什么的"

# 探索项目结构
uv run python -m tests.test_stream --task "列出当前目录下所有 Python 文件"
```

### 代码生成

```bash
# 生成代码
uv run python -m tests.test_stream --task "写一个快速排序的 Python 实现"

# 代码审查
uv run python -m tests.test_stream --task "检查 agent.py 中有哪些可以优化的地方"
```

### 技能调用

```bash
# 图像生成
uv run python -m tests.test_stream --task "生成一张宫崎骏风格的大海图像"

# 网页搜索
uv run python -m tests.test_stream --task "搜索 Python 3.13 的新特性"
```

### 指定会话追踪

```bash
# 指定 thread-id 用于 LangSmith/LangGraph 链路追踪
uv run python main.py -c -s --task_prompt "分析项目结构" --thread-id my-session-001
uv run python -m tests.test_stream --task "继续上次的分析" --thread-id my-session-001
```

### Web 界面

```bash
# 启动 Streamlit Web 界面
uv run streamlit run app.py

# 或者使用 run.sh 脚本
./run.sh --web
```

启动后访问 **http://localhost:8501**，即可使用图形化界面进行对话。

**Web 界面功能：**
- 🗨️ 多轮对话，自动保存会话历史
- 📁 会话管理：新建、切换、删除会话
- 📊 实时展示 Agent 执行 Trace（思考过程、工具调用）
- 🖼️ 支持图片、音频、视频、表格等多媒体渲染
- 🔍 会话搜索功能

### 从文件读取任务

```bash
# 将任务内容写入文件
echo "帮我写一篇关于孙悟空的散文，并用磁性男嗓音转换成音频" > task.txt

# 从文件读取任务内容，使用流式模式
uv run python main.py --task_prompt "$(cat task.txt)" -s -c

# 或者使用流式模式读取长任务
uv run python -m tests.test_stream --task "$(cat long_task.txt)"
```

## 特性

✅ 开箱即用的科研代理基座
✅ 支持自定义工具、技能、子代理扩展
✅ 本地 shell 执行能力，可直接操作本地文件、运行脚本
✅ 会话记忆持久化
✅ 兼容各类 OpenAI 协议大模型
✅ 实时流式输出，可视化执行过程
✅ 支持 LangSmith/LangGraph 链路追踪
