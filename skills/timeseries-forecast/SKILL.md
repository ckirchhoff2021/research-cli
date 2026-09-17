---
name: timeseries-forecast
description: 基于 TimesFM 3.0 基础模型的时间序列预测技能。当用户要求对时间序列/时序数据做未来预测、外推、走势预估、销量/流量/指标预测、预测回测评估（MAE/MAPE）、置信区间/分位数预测时使用本技能。支持单变量与多变量、CSV/JSON 输入、缺失值填充与重采样。不适用于纯文本分析、因果推断或分类任务。
---

# 时序预测技能（TimesFM 3.0）

封装已部署的 TimesFM 3.0 HTTP 服务（默认 `http://10.37.9.155:8333`），
用预训练时序基础模型做零样本（zero-shot）未来预测，无需为每份数据训练模型。

## 何时使用

- 有一段等间隔的历史数值（≥32 个点），想预测未来若干步，并给出分位数区间
- 单变量或多个变量并行预测；评估预测可信度（留出回测，对比朴素基线）
- 典型对象：销量、流量、PV/DAU、传感器读数、能耗、股价式连续指标等

## 服务端硬性约束（违反会被 400/422 拒绝）

- `context` 只支持 1D `[T]` 或 2D `[V,T]`，**时间长度 T ≥ 32**
- `horizon` 范围 **1..2048**
- 序列不能含 `NaN`/`inf`；多变量各序列必须**等长**
- 服务端不做预处理：真实业务数据先处理缺失/异常值、重采样到固定间隔

## 使用流程

### 1. 健康检查（服务不可达时先跑）

```bash
.venv/bin/python skills/timeseries-forecast/scripts/forecast.py health
```

### 2. 预测

输入三选一：`--csv`（推荐真实数据）、`--json`、`--values`（快速验证）。

```bash
# CSV 单变量 + 时间列 + 重采样 + 缺失值线性填充 + 回测
.venv/bin/python skills/timeseries-forecast/scripts/forecast.py forecast \
  --csv data/sales.csv --time-col date --value-col sales \
  --resample 1D --fill linear --horizon 30 --backtest 14

# CSV 多变量（多个数值列即为多条序列，按 [V,T] 发送）
.venv/bin/python skills/timeseries-forecast/scripts/forecast.py forecast \
  --csv data/metrics.csv --time-col ts --value-col pv,uv,orders --horizon 24

# JSON：1D 数组 [T] 或 2D 数组 [V,T]
.venv/bin/python skills/timeseries-forecast/scripts/forecast.py forecast \
  --json series.json --horizon 32

# 行内数值快速验证
.venv/bin/python skills/timeseries-forecast/scripts/forecast.py forecast \
  --values "10,11,12,...,45" --horizon 8
```

### 3. 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--csv/--json/--values` | 输入源，三选一 | 必填 |
| `--value-col` | CSV 数值列；多变量逗号分隔多个列名 | CSV 必填 |
| `--time-col` | CSV 时间列名；给出后按时间排序、预测时间戳可读 | 无 |
| `--resample` | pandas 频率重采样（均值聚合），如 `15min/1h/1D`，需 `--time-col`；旧写法 `1H/1T` 自动归一化 | 不重采样 |
| `--fill` | 缺失/inf 填充：`linear/ffill/bfill/mean/zero` | `linear`（双向线性插值） |
| `--horizon` | 预测步数，1..2048 | 32 |
| `--no-quantiles` | 关闭分位数输出 | 默认返回 9 个分位数 |
| `--symmetric-averaging` | 透传 TimesFM 对称平均（推理平滑选项） | 关 |
| `--backtest N` | 留出末尾 N 点做回测，输出 MAE/RMSE/MAPE 及对比朴素基线的改进幅度 | 0（不回测） |
| `--out` | 输出目录 | `outputs/timesfm_forecast/run_<时间戳>` |
| `--base-url` | 覆盖服务地址；也可用环境变量 `TIMESFM3_BASE_URL` | 内网默认地址 |

### 4. 输出（每次运行落盘）

- `forecast.csv`：预测中位数 + 9 个分位数列（多变量为每变量一组宽列），含未来步长/时间戳
- `summary.json`：参数、预处理统计（填充点数、重采样长度）、回测指标、服务延迟、文件索引
- `forecast.png`：历史（蓝）+ 未来预测（红）+ 分位数带（多变量为分面小图；回测时绿色为真实留出值、橙色为回测预测）

终端同时打印回测指标与预测前 6 个点的预览。

## 数据处理决策指引

- **频率不规律**：用 `--time-col + --resample` 固定间隔（TimesFM 假设等间隔，这一步最重要；pandas 3 用小写 `1h/15min`，`1H` 旧别名也兼容）
- **缺失值**：默认 `linear`；强趋势/季节数据线性插值即可，长缺口考虑 `ffill`，并在结论中说明
- **异常值**：服务端不处理。明显离群点建议先在数据侧 winsorize/截尾，否则模型会跟随异常波动
- **至少 32 点**：不足时无法调用；且历史越长、覆盖的周期越完整，季节预测越稳（建议 ≥2 个完整季节周期）
- **预测别外推过远**：模型支持到 2048 步，但可信区间会随时程变宽；结合 `--backtest` 的误差判断可用 horizon
- **业务含义**：零样本基础模型适合基线预测与趋势/季节延续；需要外生变量（促销、天气）或精细调优时，本技能只提供基线

## 故障排查

- `无法连接服务`：先 `health`；确认内网/VPN 与 `TIMESFM3_BASE_URL`
- `时间长度至少 32`：补数据，或降低重采样粒度（如 1H→1D 会变短，注意方向）
- `HTTP 400 all variates must have the same length`：多变量等长错误，用 CSV 读入可天然对齐，JSON 需自行补齐
- `HTTP 400 context contains NaN or inf`：指定 `--fill`；整列为空时换策略或剔除该列
- `HTTP 422`：参数类型/范围错误（如 horizon 越界），按响应 detail 修正

## 参考

- 服务 HTTP 契约与错误码：`references/timesfm3_api.md`（排查接口层问题时阅读）
