# TimesFM3 HTTP Service

把 Google TimesFM 3.0 时间序列预测模型暴露成 HTTP 接口服务，支持单变量/多变量预测。

## 文件说明

- `timesfm3_http_server.py` — FastAPI 服务端
- `timesfm3_http_examples.py` — Python 调用示例

## 环境依赖

```bash
pip install timesfm torch fastapi uvicorn numpy pydantic
```

需要提前下载 TimesFM 3.0 权重到本地。

## 启动服务

```bash
python timesfm3_http_server.py --host 0.0.0.0 --port 8333 --device cpu
```

参数：
- `--host`: 监听地址，默认 `0.0.0.0`
- `--port`: 端口，默认 `8333`
- `--device`: `auto` / `cpu` / `cuda`
- `--checkpoint`: 权重目录路径

## 健康检查

```bash
curl http://127.0.0.1:8333/health
```

## 预测接口

```bash
curl -X POST http://127.0.0.1:8333/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "context": [50,51,52,...,80,81],
    "horizon": 8,
    "return_quantiles": true
  }'
```

## 输入约束

- `context`：单变量 `(T,)` 或多变量 `(V, T)` 数值数组
- 时间长度至少 32
- 不支持 NaN/inf
- `horizon`：1~2048
