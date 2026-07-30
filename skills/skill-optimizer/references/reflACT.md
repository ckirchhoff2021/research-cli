# ReflACT 执行流程

本文档用于补充 [../SKILL.md](../SKILL.md) 中的`reflACT`执行流程，供执行 Skill 优化任务时参考。

`ReflACT (Reflective Action)` 是一种基于反思的六阶段迭代方案。它把 Skill 文档视为可优化对象，通过“执行 → 反思 → 合并 → 选择 → 更新 → 验证”的闭环持续提升效果。

除非另有说明，下面所有命令都默认在 `skills/skill-optimizer/scripts` 目录下执行，因此：

- 产物路径统一使用 `../outputs/...`
- 模板路径统一使用 `../assets/...`
- 脚本路径统一使用当前目录下的脚本名
- 以下路径中的 `<run_id>` 均沿用主文档准备阶段自动生成的本次运行目录标识；单次 ReflACT 运行的全部产物统一保存在 `../outputs/<skill-name>/<run_id>/` 目录下

为避免在正文中重复书写长路径，下面统一使用以下别名：

```text
RUN_ROOT = ../outputs/<skill-name>/<run_id>
REFLACT_ROOT = RUN_ROOT/reflact
EPOCH_ROOT = REFLACT_ROOT/<epoch_id>
```

六阶段流水线如下：

```text
[1] Rollout（推理）
  → [2] Reflect（反思，生成文本梯度）
    → [3] Aggregate（合并梯度）
      → [4] Select（裁剪梯度，保留 top-L）
        → [5] Update（更新技能文档）
          → [6] Evaluate（验证门控）
```

| 阶段 | 类比 | 说明 |
|------|------|------|
| Rollout | Forward Pass | 用当前 Skill 对训练样本执行推理，收集结果和轨迹 |
| Reflect | Backward Pass | 分析失败/成功案例，生成结构化编辑 patch（文本梯度） |
| Aggregate | Gradient Merge | 合并多个 patch，去重消歧 |
| Select | Gradient Clipping | 按重要性排序，裁剪到 top-L（L = 编辑预算） |
| Update | Optimizer.step | 应用编辑，生成候选 Skill |
| Evaluate | Validation Gate | 在验证集上评估候选 Skill，决定 ACCEPT / REJECT |


## 适用范围

当需要对某个目标 Skill 做`ReflACT`优化时，使用本流程。

## 执行流程

### 1. 准备阶段

1. `task`数据划分：
   - 将 `task` 中的任务列表按 `8:2` 的比例划分为训练集和验证集，保存在目录 `REFLACT_ROOT/`，分别命名为 `train.json` 和 `val.json`。

### 2. 静态检查阶段

1. 检查目标 Skill 包结构是否符合规范：
   - 是否存在 `SKILL.md`
   - frontmatter 是否完整
   - `name`、`description` 是否可用于路由
2. 检查文档内容与脚本实现是否一致：
   - 入参说明是否真实
   - 输出格式是否真实
   - 路径、命令、引用文件是否存在
   - 对代码进行`review`, 确保没有明显的逻辑错误，分析对边界场景的处理是否合理
3. 按评分标准 [rubric](../assets/rubric.md) 对目标 Skill 进行分析，将分析报告保存在 `RUN_ROOT/static-analysis.md` 中。
4. 如果结构或内容明显不符合 Skill 格式规范，应先提示路径或格式问题，再决定是否进入执行阶段。


### 3. 技能初始化

1. 将待优化的目标 Skill 从 `RUN_ROOT/origin/` 拷贝到 `REFLACT_ROOT/best/` 目录下，根据静态检查的结果 `static-analysis.md`，对拷贝的技能包进行初始编辑，确保其符合 Skill 格式规范，同时修改掉一些明显的代码错误。
2. 将编辑记录保存到 `REFLACT_ROOT/applied_patches.md` 文件中。

```bash
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
mkdir -p "$REFLACT_ROOT/best/"
cp -r "$RUN_ROOT/origin/"* "$REFLACT_ROOT/best/"
touch "$REFLACT_ROOT/applied_patches.md"
```

### 4. 初始验证集精度评估

#### 验证集技能 Rollout

使用 [executor.py](../scripts/executor.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
python executor.py \
  --skill "$REFLACT_ROOT/best/" \
  --task "$REFLACT_ROOT/val.json" \
  --trace_file "$REFLACT_ROOT/val_trace_origin.json"
```
当前 [executor.py](../scripts/executor.py) 会将全部任务轨迹写入 `--trace_file` 指定的文件`val_trace_origin.json`。

#### 验证集精度评估

使用 [evaluator.py](../scripts/evaluator.py) 对执行结果进行精度评估：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
python evaluator.py \
  --trace_file "$REFLACT_ROOT/val_trace_origin.json" \
  --system_prompt "../assets/judge.md"
```
将`Accuracy`的值按如下格式记录到`REFLACT_ROOT/accuracy.md`文件中。

```text
origin_accuracy=<Accuracy>
best_accuracy=<Accuracy>
```

### 5. ReflACT 核心训练Loop

在每个训练轮次中，重复执行以下六阶段, 直到达到最大训练轮数 max_epochs, `max_epochs`默认值为3, 初始`epoch_id`为0。

若出现以下任一条件，可以提前停止，不必机械跑满 3 轮：
- 当前 `best_accuracy` 已经饱和 (大于`0.98`)，或者最近两轮候选 Skill 未提升验证集精度；
- 失败样本表明瓶颈主要位于目标 Skill 的脚本/检索/推理代码，而不是 `SKILL.md` 文案；

若提前停止，必须在最终报告中明确记录停止原因和证据。

#### 阶段 1: Rollout（训练集推理）

使用 [executor.py](../scripts/executor.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python executor.py \
  --skill "$REFLACT_ROOT/best/" \
  --task "$REFLACT_ROOT/train.json" \
  --trace_file "$EPOCH_ROOT/train_trace.json"
```
当前 [executor.py](../scripts/executor.py) 会将全部任务轨迹写入 `--trace_file` 指定的文件`train_trace.json`。

随后使用 [evaluator.py](../scripts/evaluator.py) 对训练集执行结果做评估，并同时收集任务执行成功/失败样本：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python evaluator.py \
  --trace_file "$EPOCH_ROOT/train_trace.json" \
  --system_prompt "../assets/judge.md" \
  --successes_file "$EPOCH_ROOT/success_cases.json" \
  --failures_file "$EPOCH_ROOT/failure_cases.json"
```

成功案例保存到`EPOCH_ROOT/success_cases.json`，失败案例保存到`EPOCH_ROOT/failure_cases.json`。

将训练集`Accuracy`的值按如下格式追加到`REFLACT_ROOT/accuracy.md`文件中。
```text
<epoch_id>_train_accuracy=<Accuracy>
```


#### 阶段 2: Reflect（反思，生成文本梯度）

分别对失败案例和成功案例进行反思分析，生成结构化编辑建议（`proposal`）。

先查询`REFLACT_ROOT/rejected_patches.json`是否存在，该文件记录的是历史被拒绝的编辑，生成`proposal`时需要排除这些编辑。若不存在，则创建该文件，内容为空列表。

##### 对成功案例反思分析
使用 [reflector.py](../scripts/reflector.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python reflector.py \
  --enable_thinking \
  --cases_file "$EPOCH_ROOT/success_cases.json" \
  --reflect_template "../assets/refl-success.md" \
  --rejected_patches "$REFLACT_ROOT/rejected_patches.json" \
  --skill_md "$REFLACT_ROOT/best/<skill-name>/SKILL.md" \
  --case_type "success" \
  --output_file "$EPOCH_ROOT/success_patches.json"
```
基于成功案例反思生成编辑`proposal`, 并将`proposal`保存到`EPOCH_ROOT/success_patches.json`文件中。


##### 对失败案例反思分析
使用 [reflector.py](../scripts/reflector.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python reflector.py \
  --enable_thinking \
  --cases_file "$EPOCH_ROOT/failure_cases.json" \
  --reflect_template "../assets/refl-failure.md" \
  --rejected_patches "$REFLACT_ROOT/rejected_patches.json" \
  --skill_md "$REFLACT_ROOT/best/<skill-name>/SKILL.md" \
  --case_type "failure" \
  --output_file "$EPOCH_ROOT/failure_patches.json"
```
基于失败案例反思生成编辑`proposal`, 并将`proposal`保存到`EPOCH_ROOT/failure_patches.json`文件中。


#### 阶段 3: Aggregate（proposal 合并）

合并阶段2生成的编辑`proposal`，生成待应用的编辑`merged_patches`。
使用[aggregate.py](../scripts/aggregate.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python aggregate.py \
  --enable_thinking \
  --success_patches "$EPOCH_ROOT/success_patches.json" \
  --failure_patches "$EPOCH_ROOT/failure_patches.json" \
  --skill_md "$REFLACT_ROOT/best/<skill-name>/SKILL.md" \
  --output_file "$EPOCH_ROOT/merged_patches.json" \
  --aggregate_template "../assets/aggregate.md"
```
将`merged_patches`保存到`EPOCH_ROOT/merged_patches.json`文件中。

#### 阶段 4: Select（梯度裁剪, clip）

对阶段3生成的`merged_patches`进行裁剪，生成`selected_patches`，保留 top-L（L = 编辑预算）个编辑，默认编辑预算为5个 patch。
使用[clip.py](../scripts/clip.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python clip.py \
  --enable_thinking \
  --merged_patches "$EPOCH_ROOT/merged_patches.json" \
  --skill_md "$REFLACT_ROOT/best/<skill-name>/SKILL.md" \
  --edit_budget 5 \
  --output_file "$EPOCH_ROOT/selected_patches.json" \
  --clip_template "../assets/clip.md"
```
将裁剪后的编辑保存到`EPOCH_ROOT/selected_patches.json`文件中。

#### 阶段 5: Update（更新技能文档, rewrite）

使用阶段4生成的编辑`selected_patches`，对技能进行重写，生成新的技能文档。
使用 [step.py](../scripts/step.py) 执行任务：

```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python step.py \
  --enable_thinking \
  --selected_patches "$EPOCH_ROOT/selected_patches.json" \
  --skill_md "$REFLACT_ROOT/best/<skill-name>/SKILL.md" \
  --output_file "$EPOCH_ROOT/SKILL.md" \
  --rewrite_template "../assets/rewrite.md"
```
将重写后的技能文档保存到`EPOCH_ROOT/SKILL.md`文件中。


#### 阶段 6: Evaluate（验证门控）

在验证集上评估新生成的技能文档：
- 将当前推理使用的技能`REFLACT_ROOT/best/<skill-name>/`拷贝到目录`EPOCH_ROOT/update/`
- 使用阶段5生成的技能文档`EPOCH_ROOT/SKILL.md`，覆盖`EPOCH_ROOT/update/<skill-name>/SKILL.md`
```bash
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
mkdir -p "$EPOCH_ROOT/update"
cp -r "$REFLACT_ROOT/best/<skill-name>" "$EPOCH_ROOT/update/"
cp "$EPOCH_ROOT/SKILL.md" "$EPOCH_ROOT/update/<skill-name>/SKILL.md"
```
- 使用[executor.py](../scripts/executor.py) 在验证集上执行新生成的技能文档：
```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python executor.py \
  --skill "$EPOCH_ROOT/update/" \
  --task "$REFLACT_ROOT/val.json" \
  --trace_file "$EPOCH_ROOT/val_trace_update.json"
```
当前 [executor.py](../scripts/executor.py) 会将全部任务轨迹写入 `--trace_file` 指定的文件`val_trace_update.json`。
- 使用[evaluator.py](../scripts/evaluator.py) 对执行结果进行精度评估：
```bash
cd skills/skill-optimizer/scripts
RUN_ROOT="../outputs/<skill-name>/<run_id>"
REFLACT_ROOT="$RUN_ROOT/reflact"
EPOCH_ROOT="$REFLACT_ROOT/<epoch_id>"
python evaluator.py \
  --trace_file "$EPOCH_ROOT/val_trace_update.json" \
  --system_prompt "../assets/judge.md"
```
将`Accuracy`的值按如下格式追加到`REFLACT_ROOT/accuracy.md`文件中。
```text
<epoch_id>_val_accuracy=<Accuracy>
```
- 从`REFLACT_ROOT/accuracy.md`中读取`best_accuracy`，并与`<epoch_id>_val_accuracy`进行对比，按如下门控决策策略进行处理。

**门控决策：**
- `<epoch_id>_val_accuracy > best_accuracy` → **ACCEPT**（接受并更新最佳记录），更新 `best_skill`，将`EPOCH_ROOT/SKILL.md`拷贝到`REFLACT_ROOT/best/<skill-name>/`，覆盖原始 `best_skill` 中的`SKILL.md`。
    - 在`REFLACT_ROOT/accuracy.md`文件中更新`best_accuracy`为`<epoch_id>_val_accuracy`。
    - 将阶段4生成的编辑`selected_patches.json`，记录到`REFLACT_ROOT/applied_patches.md`文件中。
- `<epoch_id>_val_accuracy ≤ best_accuracy` → **REJECT**（拒绝，将阶段4生成的编辑`selected_patches.json`追加到`REFLACT_ROOT/rejected_patches.json`），并在下次反思中引入这些被拒绝的编辑。


### 6. 结果输出

完成 ReflACT 训练后，同时生成 Markdown 和 HTML 格式的优化报告，存放在 `REFLACT_ROOT/report/` 中。
优化报告需涵盖以下方面的内容：
1. 初始静态检查分析报告
2. 验证集初始精度，以及每个epoch的训练集和验证集精度
3. 每个epoch的编辑记录
4. 最终采纳的编辑记录和`best`技能文档路径

## 编辑操作参考

| 操作 | 说明 | 使用场景 |
|------|------|----------|
| `append` | 末尾追加 | 添加新的规则或注意事项 |
| `insert_after` | 锚点后插入 | 在特定段落后面补充细节 |
| `replace` | 替换文本 | 修正错误或改进现有规则 |
| `delete` | 删除文本 | 移除冗余或有害的规则 |

## 重要原则

1. **失败优先**：修复错误的编辑优先于强化成功的编辑
2. **避免重复**：`rejected_patches.json` 记录历史被拒编辑，防止循环尝试相同修改
3. **小步迭代**：每步编辑预算有限，避免一次性大幅修改
4. **验证驱动**：只有验证集分数提升才接受编辑，防止技能退化
5. **缓存复用**：记录历史所有的编辑记录，避免相同的编辑重复应用


## 中间产物

一个典型的 ReflACT 训练过程会产生如下中间产物：

```text
outputs/<skill-name>/
└── <run_id>/
    ├── origin/
    │   └── <skill-name>/
    │       ├── SKILL.md
    │       ├── references/
    │       ├── scripts/
    │       └── assets/
    ├── static-analysis.md
    └── reflact/
        ├── train.json
        ├── val.json
        ├── val_trace_origin.json
        ├── accuracy.md
        ├── applied_patches.md
        ├── rejected_patches.json
        ├── best/
        │   └── <skill-name>/
        │       ├── SKILL.md
        │       ├── references/
        │       ├── scripts/
        │       └── assets/
        ├── <epoch_id>/
        │   ├── train_trace.json
        │   ├── success_cases.json
        │   ├── failure_cases.json
        │   ├── success_patches.json
        │   ├── failure_patches.json
        │   ├── merged_patches.json
        │   ├── selected_patches.json
        │   ├── SKILL.md
        │   ├── update/
        │   │   └── <skill-name>/
        │   │       ├── SKILL.md
        │   │       ├── references/
        │   │       ├── scripts/
        │   │       └── assets/
        │   └── val_trace_update.json
        └── report/
            ├── report.md
            └── report.html
```

这些文件分别承载：

- `origin/<skill-name>/`：本次运行备份的原始完整 Skill 包
- `static-analysis.md`：目标 Skill 的初始静态检查结论
- `train.json` / `val.json`：按训练集和验证集拆分后的任务集
- `val_trace_origin.json`：初始 best Skill 在验证集上的执行轨迹
- `accuracy.md`：初始精度以及各 epoch 的训练/验证精度变化
- `applied_patches.md`：被 ACCEPT 的编辑历史
- `rejected_patches.json`：被 REJECT 的编辑历史，供后续反思阶段避让
- `best/<skill-name>/`：当前被接受的最佳 Skill 副本
- `<epoch_id>/train_trace.json`：该轮训练集 rollout 轨迹
- `<epoch_id>/success_cases.json` / `failure_cases.json`：从训练轨迹中拆分出的成功/失败样本
- `<epoch_id>/success_patches.json` / `failure_patches.json`：基于成功/失败样本生成的反思编辑 proposal
- `<epoch_id>/merged_patches.json`：聚合后的 patch 集
- `<epoch_id>/selected_patches.json`：裁剪后的最终 patch 集
- `<epoch_id>/SKILL.md`：根据所选 patch 重写出的候选技能文档
- `<epoch_id>/update/<skill-name>/`：用于验证门控的候选 Skill 包目录
- `<epoch_id>/val_trace_update.json`：候选 Skill 在验证集上的执行轨迹
- `report/report.md` / `report/report.html`：最终优化报告
