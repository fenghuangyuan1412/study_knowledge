# 本地知识库 Web 问答页（web/）

在浏览器里直接向「AI软件测试」知识库提问的后端与页面（main 分支维护）。

## 运行前提

1. localbrain 已安装并初始化（数据在 `~/.knowledge-base`，配置 `~/.localbrain/config.yaml`）
2. 知识内容已收集（`kb/<方向>/batch-*/items/*.md` → `localbrain collect file add`，可选 `localbrain mine` 向量化）

## 启动 / 停止

```powershell
# 启动（默认 http://127.0.0.1:18765 ）
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action start

# 停止
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action stop

# 查看状态/日志
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action status
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action logs
```

启动后打开浏览器访问 `http://127.0.0.1:18765` 即可问答，无需 agent 介入。

## 后端能力（三级自动降级）

| 配置情况 | 返回 |
| --- | --- |
| 已配 嵌入 + LLM（DashScope / new-api / Ollama） | AI 生成式回答 + 引用来源（RAG） |
| 已配 嵌入、未配 LLM | 相关文档片段列表（语义检索，无 AI 总结） |
| 均未配 | 关键词检索片段（仍可查） |

- 页面状态栏会显示当前处于哪种模式。
- 服务端口可用环境变量 `PORT` 覆盖；绑定地址 `HOST`（默认 127.0.0.1）。
- 已开启 CORS，便于日后被其他本地页面 iframe/接口对接。

## 后端切换说明（DashScope ↔ new-api/Ollama）

编辑 `~/.localbrain/config.yaml`（注意：该文件在仓库外、不会提交 git）：

- DashScope（免费额度）：`embedding.dashscope.api_key` / `llm.dashscope.api_key` 填 `sk-...`
- 本地 new-api（OpenAI 兼容，代理 Ollama）：把 `embedding.provider` 与 `llm.provider` 改为 `openai_compatible`，
  并填写 `embedding.openai_compatible.{api_key,base_url,model}` 与 `llm.openai_compatible.{api_key,base_url,model}`。

改完重启服务即可；页面状态栏会自动反映新模式。
