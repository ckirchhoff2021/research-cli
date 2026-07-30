---
name: skill-optimizer
description: 优化和评测现有 Skill。用于执行目标 Skill、采集和分析执行轨迹、定位触发与工具调用问题，并输出可落地的优化建议。当用户要求优化 skill、分析 skill 执行过程、采集技能 trace、做技能评测或改进技能效果时使用。
---

# Skill Optimizer

用于对现有 Skill 做执行级分析和优化，不直接凭空评价 Skill，而是先运行目标 Skill、记录轨迹，再基于证据提出改进建议。

## 何时使用

当出现以下场景时使用本技能：

- 用户要求优化、改进、迭代某个 Skill
- 用户想看某个 Skill 的执行过程、工具调用链路或 trace
- 用户认为某个 Skill 效果不好，希望定位问题
- 用户需要对 Skill 做回归测试、样例评测、对比分析

## 必要输入

开始执行前，至少确认以下信息：

| 参数 | 是否必填 | 说明 |
|---|---|---|
| `skill` | 是 | 目标 Skill 的路径，必须直接指向目标 Skill 根目录，且该目录下必须包含 `SKILL.md` 文件。 |
| `task` | 是 | 用于触发目标 Skill 的测试任务。既可以是单条自然语言任务，也可以是一个 JSON 文件路径；JSON 输入中至少应包含 `query` 字段，可选包含 `expected` 字段。 |
| `trace_file` | 否 | 执行阶段的轨迹输出文件路径。该参数主要用于常规分析流程或调试；若不传，脚本会自动生成 `trace_YYYYMMDD_HHMMSS.json`。 |

如果用户没有提供可执行的测试任务，先帮助用户补齐 1 到 3 条有代表性的真实样例，再开始执行，生成的样本保存在 `outputs/<skill-name>/gen_tasks.json` 文件中,格式如下：
```json
[
  {
    "query": "用户输入的任务",
    "expected": "可选的期望输出或验收标准"
  }
]
```

如果 `task` 是 JSON 文件路径，当前 `executor.py` 支持单个 `{query, expected}` 对象、任务数组，以及包含 `tasks` 数组的对象；脚本会提取每个任务的 `query` 字段，并保留 `expected` 字段用于后续评测或路由判断。

首次运行前，需检查 `scripts/.env` 的环境配置，若配置不完整，提醒用户在 `scripts/.env` 中补齐以下配置：

| 配置组 | 变量 | 用途 |
|---|---|---|
| `BRAIN_API` | `BRAIN_API_KEY` / `BRAIN_API_URL` / `BRAIN_MODEL_NAME` | 用于在 Harness 环境中执行目标 Skill |
| `OPTIMIZER_API` | `OPTIMIZER_API_KEY` / `OPTIMIZER_API_URL` / `OPTIMIZER_MODEL_NAME` | 用于评测和优化目标 Skill |

若用户在上下文中提供了相应配置，先写入 `scripts/.env`，重新检查配置完整性，再次执行任务。

除上述 API 配置外，还需确认 Python 运行环境已安装 `skill-optimizer` 自身依赖。当前 Skill 已在包内提供依赖清单 `assets/requirements.txt`；若环境不满足，需先安装依赖，再执行任务。


## 执行目标

每次执行本技能时，必须完成以下四件事：

1. 确认目标 Skill 路径，对 Skill 进行静态评测
2. 运行目标 Skill，获得真实输出
3. 记录执行轨迹，包括工具调用、关键中间步骤和最终结果
4. 基于轨迹分析 Skill 的问题，并输出结构化优化建议

实际执行时，应先根据任务规模和数据结构完成路由，再进入对应的常规分析流程或 `reflACT` 迭代流程。

## 执行流程

### 准备阶段

1. 检查 `skill` 入参是否正确，并备份原始 Skill：
   - `skill` 必须直接指向目标 Skill 根目录，且该目录下必须包含 `SKILL.md`。
   - 若输入目录下不存在 `SKILL.md`，则返回错误信息并终止执行。
   - 从 `SKILL.md` 中识别技能名称 `<skill-name>`。
   - 创建备份目录 `outputs/<skill-name>/origin/`。
   - 将该 Skill 根目录整体复制到 `outputs/<skill-name>/origin/` 下。
   - 将实际执行用的 `skill` 路径调整为 `outputs/<skill-name>/origin/`。
   ```bash
   mkdir -p outputs/<skill-name>/origin/
   cp -r <skill-root> outputs/<skill-name>/origin/
   ```

2. 检查 `task` 入参是否可执行：
   - 若为普通字符串，则直接作为单条任务执行。
   - 若为文件路径，则按 JSON 读取，并从每个对象的 `query` 字段中提取任务；若存在 `expected` 字段，则一并保留用于评测。
   - 若任务数据缺少 `expected` 或验收要求，可继续执行，但应在分析阶段明确标注“仅做开放式评估”。

### 任务路由

检查 `task` 入参，根据任务规模和标注完备度按如下规则进行路由：

- 若 `task` 是带有 `expected` 字段的 JSON 任务集，且有效任务数量超过 20 条，则采用 [reflACT](references/reflACT.md) 方案对目标 Skill 进行评测和优化。
- 单条自然语言任务、缺少 `expected` 的开放式任务集，或样本量较小的 JSON 任务集，均采用常规流程 [analysis](references/analysis.md) 对目标 Skill 进行分析和优化。

## 参考资源

- 常规执行流程：`references/analysis.md`
- `reflACT` 执行流程：`references/reflACT.md`

## 注意事项
本文档中的 `outputs/...` 表示 `skill-optimizer` 根目录下的产物目录；若按参考文档中的命令在 `scripts/` 目录执行，则对应路径写法为 `../outputs/...` 和 `../assets/...`。
