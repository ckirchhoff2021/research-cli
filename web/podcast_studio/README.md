# 🎙 Podcast Studio · AI 播客创作工坊

参考 Image Studio 的架构打造：写好台词、选好主播音色，一键合成完整播客节目。

## 特性

- **多主播对话脚本**：每段台词独立指定音色，支持主播 A / B 快捷位、段落排序与删除
- **348 款在线音色**：按语种 / 场景筛选、关键词搜索、任意音色即时试听
- **长文本自动切块**：超过 350 字按句切分多次合成，再用 ffmpeg 无缝拼接
- **语速 / 音量 / 音调调节**：0.8–1.5 全局滑杆
- **整期节目合成**：逐段 TTS → ffmpeg `concat` 输出整期 MP3，自动保留单段片段
- **音频库管理**：在线试听、下载、删除
- **🤖 AI 编剧**：输入一个主题，自动生成吸引人的标题和主播对白，载入后可直接成片

## 启动

```bash
cd /Users/chenxiang/Downloads/Git/research-cli
./web/podcast_studio/run_studio.sh          # 默认端口 8901
# 或指定端口：./web/podcast_studio/run_studio.sh 8905
```

打开 <http://127.0.0.1:8901>，点「✨ 载入示例脚本」→「🚀 生成整期节目」即可体验。

## AI 自动写稿

在创作页点「🤖 AI 生成对白」：

- 输入任意主题（如「AI 会不会取代人类的工作」）
- 选择**节目形式**：双人对谈 / 单人讲述
- 选择**语言风格**：轻松闲聊 · 深度访谈 · 知识科普 · 搞笑脱口秀 · 商业财经 · 情感故事
- 选择**篇幅**：约 8 / 12 / 20 段

约 30~120 秒后，标题与 A/B 对白自动写入脚本（自动匹配主播 A、B 的音色），
检查或微调后点「生成整期节目」即可。底层调用火山方舟 Ark（`.env` 中
`BRAIN_API_KEY / BRAIN_MODEL_NAME`），输出强制 JSON 解析并做合法性校验。

## 目录结构

```
web/podcast_studio/
├── run_studio.sh         # 启动脚本
├── backend/
│   ├── server.py         # FastAPI：音色/试听/节目/音频库/SSE
│   ├── aiwriter.py       # AI 主题生成对白（Ark LLM）
│   ├── pipeline.py       # TTS API 调用、文本切分、ffmpeg 拼接
│   └── jobs.py           # 串行任务队列 + SSE 事件总线
└── static/               # 单页前端（index.html / styles.css / app.js）
```

生成结果按 AGENTS.md 规范归档至 `outputs/20_播客工作室/`（`clips/`、`episodes/`）。

## 依赖

- `.env` 中需配置 `TTS_APPID / TTS_ACCESS_TOKEN / TTS_CLUSTER / TTS_HOST`
- ffmpeg 自动探测：`FFMPEG_PATH` → `~/.hermes/tools/ffmpeg-*` → PATH → `imageio-ffmpeg`
