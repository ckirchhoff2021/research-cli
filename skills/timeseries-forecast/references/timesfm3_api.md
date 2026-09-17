# TimesFM3 HTTP 服务契约

基础 URL 默认 `http://10.37.9.155:8333`，可用 `TIMESFM3_BASE_URL` 或 `--base-url` 覆盖。
服务源码部署文档：`instructions/timesfm3.md`。

## GET /health

```json
{
  "status": "ok",
  "checkpoint": "/home/chenxiang.101/checkpoints/timesfm-3.0",
  "device": "cuda",
  "torch": "2.9.0+cu128",
  "cuda_build": "12.8",
  "cuda_available": true
}
```

## POST /predict

请求：

```json
{
  "context": [1, 2, 3],
  "horizon": 12,
  "return_quantiles": true,
  "use_symmetric_averaging": false
}
```

- `context`：单变量 `(T,)`；多变量 `(V, T)`（变量在外、时间在内）
- `horizon`：1..2048
- `return_quantiles`：返回 9 个分位数（p10..p90），形状 `[H, 9]` / `[V, H, 9]`
- `use_symmetric_averaging`：TimesFM 推理参数

响应：

```json
{
  "forecast": [73.76, 73.16],
  "forecast_shape": [12],
  "quantiles": [[73.70, 73.71, 73.73, 73.75, 73.76, 73.81, 73.84, 73.84, 73.85]],
  "quantiles_shape": [12, 9]
}
```

`forecast` 为中位数点预测；`quantiles` 每行对应一个未来时点的 9 个分位。

## 输入约束与状态码（2026-09-17 实测）

| 情况 | 状态码 | 响应 |
|---|---|---|
| 正常 | 200 | 预测 JSON |
| T < 32 | 400 | `{"detail": "context length must be at least 32"}` |
| NaN/inf | 400 | `{"detail": "context contains NaN or inf"}` |
| 多变量不等长 | 400 | `{"detail": "all variates must have the same length"}` |
| horizon 越界（0/-1/2049） | 422 | pydantic `greater_than_equal/less_than_equal` |
| 缺字段/空对象/非法 JSON | 422 | pydantic 结构化错误 |
| 3D 输入、非数值 | 422 | pydantic 类型校验 |

注意：严格 JSON 客户端（如新版 `requests` 的 `json=`）无法序列化 `NaN/Infinity` token，
会在客户端先抛 `InvalidJSONError`；技能脚本因此在发送前完成填充/拒绝，不依赖服务端兜底。

## 性能参考（CUDA 模式实测）

- T=128/H=24 含分位数 ≈ 0.2s
- T=2048/H=64 ≈ 0.25s
- H=2048（上限）≈ 0.7s

零样本质量抽查：干净趋势+季节序列 48 步 MAE≈0.04；带噪季节序列较朴素（末值平移）基线 MAE 降低约 80%。
