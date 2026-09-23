# OPD / OPSD 领域知识浓缩（2026-08 知乎调研沉淀）

再遇大模型后训练蒸馏主题可直接复用。数据来源：知乎 20+ 篇深度文章 + 原始出处锚点；实验数字为社区转述，正式引用前建议二次核对。

## 一句话定位
- **OPD（On-Policy Distillation）** = 学生自己采样（on-policy 相关性）+ 教师逐 token 分布监督（dense）。解决 SFT 暴露偏差 + RL 信号稀疏。
- **OPSD（On-Policy Self-Distillation）** = OPD 去外部教师版：教师 = 同模型 + 特权信息 PI（参考答案），"开卷的自己教闭卷的自己"。

## 核心公式
```
标准目标:   L = E_{ŷ~πθ} [ Σ_t KL( πθ(·|x,y_<t) ‖ ν(·|x,y_<t) ) ]   (reverse-KL)
PG-OPD:    A_t = log ν(y_t|y_<t) − log πθ(y_t|y_<t)   → 当 dense advantage 走 PPO-clip
OPSD:      L = E [ Σ_t D( πθ(·|x,y_<t) ‖ sg[πθ(·|x,PI,y_<t)] ) ], 教师=初始策略快照
散度选择:   FKL mode-covering（需教师采样，sampled-token 有偏）；RKL mode-seeking（与学生采样自洽）；JSD 对称有界（GKD 默认）
```
reverse-KL 是 sampled-token OPD 的理论根基：KL(πθ‖ν) 可写成学生分布上的期望，单 token 采样即一次 MC 估计。

## 监督粒度三变体
sampled-token（最省，业界主流）/ top-k（top-16，须重归一化否则梯度有偏）/ full-vocab（最贵 O(B·T·V)，监督最全；OPSD 论文中优于 sampled-token）。

## 关键事实与数据（均为转述）
- Thinking Machines 博客（Kevin Lu, 2025-10-27, DOI:10.64434/tml.20251026）：OPD 用 ~1/10 RL 算力，AIME'24 反超 6.8 分；recipe = KL 正则 RL 脚本把 reference model 换成 teacher。受 Qwen 启发（提及 38 次）。代码：tinker-cookbook recipes/distillation。
- OPSD 论文（Self-Distilled Reasoner, arXiv:2601.18734, UCLA/HKU/Meta）：Qwen3-8B/4B/1.7B 上匹配或超 GRPO（1.7B: 37.1→43.4），token 效率 8-12×；full-vocab 优于 sampled-token（84.1/60.0 vs 82.1/57.3）；SFT 反而退化（模仿简洁风格损害泛化）。
- 工业标配：Qwen3、GLM-5、MiMo-v2-flash、DeepSeek-V4 后训练收尾用 OPD/MOPD 做"能力合并"（RL 练偏科专家 → OPD 迁回基座）。

## 病理 → 修复速查（报告第四章核心）
| 病理 | 修复 |
|---|---|
| 学生前缀扭曲教师分布（教出 Wait/But 纠碎片段） | SFT 冷启动拉近分布 |
| Top-K RKL 未归一化梯度偏差 → 崩溃 | 重归一化 / stop-gradient |
| 更强教师反而更差（OPD 是探索催化剂不抬上限） | advantage hard-clip + log-compression |
| 特权诱导风格偏移（信号被风格 token 主导） | RLCSD：对比正确/错误提示下师生差异 |
| 长 CoT 死记硬背（反思词崩塌或复读） | Purified OPSD：对照教师 + PMI 提纯残差 |
| 轨迹绑死（偏离参考解即全局重写） | Rubric-SD：用评分标准替代单条参考解 |
| 输出空间信号饱和（平台期） | OPRD：中间层隐藏状态 MSE 对齐 |

## 演进谱系
GKD/MiniLLM(2023-24) → TML OPD/Qwen3(2025.10) → OPSD/SDPO(2026.01) → SRPO/RLSD/Lightning-OPD/OPSDL(2026.04) → MiMo-MOPD/机理研究(Rethinking 2604.13016, Demystifying 2607.13399, Many Faces 2605.11182)。
数学统一：G-OPD 证明 OPD ≡ KL 正则 RL（teacher log-ratio = 隐式奖励）。

## 消歧
- "OPSD" 有两个：Self-Distilled Reasoner（PI=ground truth）vs π-Distill 的 OPSD 模块（PI=强模型动作轨迹）。
- OPD 是采样/监督协议；KL 反传 vs policy gradient 是正交的优化协议选择。

## 原始出处锚点
thinkingmachines.ai/blog/on-policy-distillation · GKD(Agarwal 2024) · MiniLLM(ICLR'24) · arXiv:2601.18734 · thunlp/OPD
