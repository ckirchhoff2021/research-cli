# research-cli

一个基于 DeepAgents 框架的科研工作流命令行工具，帮助自动化日常科研任务。

## 架构概览

```
research-cli/
├── main.py                # 命令行入口，接收任务参数调用代理
├── agent.py               # 核心代理初始化逻辑
├── pyproject.toml         # 项目配置与依赖管理
├── uv.lock                # uv 依赖锁定文件
├── .env / .env.example    # 环境变量配置
├── memory/                # 代理长期记忆存储，包含 AGENTS.md 行为规范
├── skills/                # 自定义技能集，扩展代理专项能力
├── tools/                 # 自定义工具实现，供代理调用
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

## 运行模式

| 模式 | 命令 | 说明 |
|------|------|------|
| 普通模式 | `uv run python main.py --task_prompt "..."` | 一次性输出最终结果 |
| 控制台模式 | `uv run python main.py -c --task_prompt "..."` | 树形结构展示执行过程 |
| 流式模式 | `uv run python main.py -c -s --task_prompt "..."` | 实时流式刷新执行过程 |

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
