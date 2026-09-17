# server-tools

独立可部署的模型服务工具集，将各类 AI 模型封装为 HTTP API 供 research-cli 或其他系统调用。

## 工具列表

| 工具 | 端口 | 说明 |
|------|------|------|
| [timesfm3](timesfm3/) | 8333 | Google TimesFM 3.0 时间序列预测服务 |

## 通用使用流程

1. 进入对应工具目录
2. 安装依赖并下载模型权重
3. 启动 HTTP 服务
4. 通过 HTTP API 或 Python 客户端调用
