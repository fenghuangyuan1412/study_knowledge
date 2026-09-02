# 本地知识库 Web 问答页（web/）

在浏览器里直接向「AI软件测试」知识库提问的后端与页面（main 分支维护）。

> ⚠️ **给自己的提醒（重要）**：先用阿里云 DashScope 免费额度把整库与问答跑通；免费额度用完 / 想完全本地化后，
> **切换成本地模型**——把 `~/.localbrain/config.yaml` 的 `embedding`/`llm` 两段改成走本地 **new-api（OpenAI 兼容）接 Ollama**
> （改 provider/model/api_key/base_url 四字段，重启服务即可，页面状态栏会自动切换模式）。本仓库所有文件不含任何 key。


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

## 当前接线（2026-09-03 · 全本地 Ollama，无需任何云端 key）

- 嵌入：`ollama/bge-m3`（1024 维，中文优先）；对话：`ollama/qwen3.5:9b`
- 直连 `http://127.0.0.1:11434`（Ollama，Windows 原生进程）；本机另有 new-api（WSL+Docker，`127.0.0.1:3000`）可作统一网关，切换见下节
- 访问方式只读出站调用，不影响 new-api/Ollama 本体；本服务只绑 `127.0.0.1:18765`，与 `3000/11434` 无冲突

### 运维备忘（踩坑记录）

1. **chroma 向量只在“收集”时写入**（`mine` 只写 sqlite）。若收集时没配好嵌入服务（历史 401），需对已入库文件补索引：
   读 `~/.knowledge-base/1_collect/**/*.md` 的 frontmatter（用正则解析 id/title/tags/source，注意 source 双引号内含反斜杠不能直接 yaml 解析），对每篇调 `kb.commands.utils._index_content_for_search`。
2. **qwen3.5 默认输出在 `thinking` 字段、`content` 为空** → RAG 无回答。解法：`~/.localbrain/config.yaml` 的 `llm.think: false`，并需在 localbrain 工具环境补丁：
   `kb/query/rag.py` 的 `_call_litellm()` 中把 `llm.think` 透传为 `kwargs["think"]`。⚠️ 执行过 `localbrain self-update` 后需重新打补丁。
3. 控制台/终端里中文显示乱码仅为 GBK 显示问题，浏览器页面正常（UTF-8）。


## 后端切换说明（DashScope ↔ new-api/Ollama）

编辑 `~/.localbrain/config.yaml`（注意：该文件在仓库外、不会提交 git）：

- DashScope（免费额度）：`embedding.dashscope.api_key` / `llm.dashscope.api_key` 填 `sk-...`
- 本地 new-api（OpenAI 兼容，代理 Ollama）：把 `embedding.provider` 与 `llm.provider` 改为 `openai_compatible`，
  并填写 `embedding.openai_compatible.{api_key,base_url,model}` 与 `llm.openai_compatible.{api_key,base_url,model}`。

改完重启服务即可；页面状态栏会自动反映新模式。
