# 常规执行流程

本文档用于补充 [SKILL.md](../SKILL.md) 中的常规执行流程，供执行 Skill 优化任务时参考。

## 适用范围

当需要对某个目标 Skill 做静态检查、轨迹采集、结果分析和优化建议输出时，使用本流程。

除非另有说明，以下路径中的 `<run_id>` 均沿用主文档准备阶段自动生成的本次运行目录标识；单次常规分析的全部产物统一保存在 `../outputs/<skill-name>/<run_id>/` 目录下。

为避免在正文中重复书写长路径，下面统一使用以下别名：

```text
RUN_ROOT = ../outputs/<skill-name>/<run_id>
```

## 执行流程

### 1. 静态检查阶段

1. 检查目标 Skill 包结构是否符合规范：
   - 是否存在 `SKILL.md`
   - frontmatter 是否完整
   - `name`、`description` 是否可用于路由
2. 检查文档内容与脚本实现是否一致：
   - 入参说明是否真实
   - 输出格式是否真实
   - 路径、命令、引用文件是否存在
   - 对代码进行review, 确保没有明显的逻辑错误，分析对边界场景的处理是否合理
3. 按评分标准 [rubric](../assets/rubric.md) 对目标 Skill 进行分析，将分析报告保存在 `RUN_ROOT/static-analysis.md` 中。
4. 如果结构或内容明显不符合 Skill 格式规范，应先提示路径或格式问题，再决定是否进入执行阶段。


### 2. 轨迹采集阶段

使用 [executor.py](../scripts/executor.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
python executor.py \
  --skill "$RUN_ROOT/origin/" \
  --task "<test-task-or-json-file>" \
  --trace_file "$RUN_ROOT/trace.json"
```

其中：

- `--skill` 传给 `executor.py` 的是 Skill 搜索目录，即包含 `<skill-name>/` 子目录的上级目录，而不是直接包含 `SKILL.md` 的目录
- `--root_dir` 控制 `LocalShellBackend` 的工作目录；若不显式传入，默认使用 `--skill` 的目录
- 当目标 Skill 依赖特定 workspace 根目录时，再显式传入 `--root_dir`

如果传入的是 JSON 文件，脚本会循环处理每个 `query`，并将所有任务结果统一写入一个 trace 文件。

当前 [executor.py](../scripts/executor.py) 会将全部任务轨迹写入 `--trace_file` 指定的文件。

如果未指定 `--trace_file`，默认会在当前工作目录生成：

`trace_YYYYMMDD_HHMMSS.json`

### 3. 结果分析阶段

基于轨迹文件，从以下维度进行分析，并将分析报告保存在 `RUN_ROOT/trace-analysis.md` 中：

#### 3.1 触发是否正确

- 是否命中目标 Skill
- 是否存在误触发或漏触发
- `description` 是否足以支撑正确路由

#### 3.2 流程是否合理

- 是否遵循目标 Skill 的预期执行顺序
- 是否跳过必要步骤
- 是否存在冗余步骤或无效重复

#### 3.3 工具调用是否正确

- 工具选择是否合理
- 参数是否正确
- 工具结果是否被正确消费

#### 3.4 输出是否符合预期

- 最终结果是否满足任务要求
- 输出格式是否正确
- 是否遗漏关键字段、路径、链接或说明

### 4. 优化建议输出阶段

结合静态检查结果和轨迹执行结果，输出整体评价和优化建议报告，优化建议至少包含以下字段：

- 发现的问题
- 证据来源
- 建议修改的位置
- 推荐修改方式
- 预期收益

推荐格式：

```markdown
## 整体评价

- 静态检查结果：根据静态检查结果和推荐的修改，判断 Skill 是否符合规范。
- 轨迹执行结果：根据轨迹执行结果和推荐的修改，判断 Skill 是否符合预期。

## 优化建议

### 问题 1：重复读取技能文档
- 证据：第 2 步和第 5 步重复调用 read_file 读取同一份 SKILL.md
- 影响：增加额外工具调用和等待时间
- 建议：在单轮执行中缓存已读取的技能文档内容
- 预期收益：减少重复工具调用，缩短执行耗时
```

### 5. 编辑应用阶段

根据优化建议，对目标 Skill 进行编辑应用，注意不要直接修改原始输入 Skill，而是拷贝一份新的 Skill 到 `RUN_ROOT/update/`，并在拷贝的 Skill 中进行修改。
```bash
RUN_ROOT="../outputs/<skill-name>/<run_id>"
mkdir -p "$RUN_ROOT/update/"
cp -r "$RUN_ROOT/origin/"* "$RUN_ROOT/update/"
```

## 注意事项

1. 不要在没有执行证据时直接评价 Skill 好坏。
2. 不要只看最终答案，必须关注触发、流程和工具调用。
3. 不要在分析阶段直接覆盖原始 Skill，先输出分析和建议。
4. 如果执行失败，必须保留完整错误上下文，便于复盘。
5. 如果用户未提供训练集或验证集，先做单样例执行分析，不要伪造 benchmark 结果。
6. 不要直接修改原始输入 Skill，而是在分析阶段输出建议修改的位置和方式，并拷贝一份新的 Skill 文件进行修改。
