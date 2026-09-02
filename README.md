# 个人学习知识库

个人专用学习知识库（账号：fenghuangyuan1412）：把要学习的内容按体系组织存放，并逐步沉淀为可检索的向量知识库。

## 项目介绍

- 个人学习知识库的搭建：**每一个不同体系的知识库**都会有一段**粗略的介绍**，并附带我的**学习路线**。
- 第一个知识库：**AI 软件测试** —— 利用 AI 能力对传统软件测试进行更快节奏的测试。
- 学习内容以 md 沉淀进 git（`kb/`），同时交给 **localbrain** 向量化，由**本地 Web 问答页**直接检索问答，日常提问不再依赖 agent 手工操作。

## 结构层

- **内容层**：`kb/<方向>/batch-<编号>/items/*.md`（UTF-8 Markdown），每批固定 5 条。
- **向量引擎**：`localbrain`（数据在 `~/.knowledge-base`：`1_collect` 原文 + `db/chroma` 向量库；配置在 `~/.localbrain/config.yaml`，**均不在 git 内**）。
- **调用层**：`web/` 本地 Web 问答页（前端页面 + 后端 API，main 分支维护）。
- **工作流**：详见 `agent.md` —— 知识操作一律在 `kb/<方向>/batch-<编号>` 分支上提交，**经人工同意后**合入 main 并推送 origin，保证 main 主枝稳定、多人并发上传互不影响。

## 仓库结构（当前）

| 文件 / 目录 | 作用 |
| --- | --- |
| `README.md` | 本文件：项目介绍 + 结构 + 组件说明 + 启动方法 + 端口 |
| `agent.md` | 方向 / 结构 / git 工作流总控文件（大方向改动入口） |
| `kb/ai-software-testing/` | 第一个知识库「AI软件测试」的内容（batch-001 首批 5 条已入库） |
| `web/` | 本地 Web 问答页：前端页面 + 后端服务 + 启动脚本（详见 `web/README.md`） |
| `Dockerfile` / `docker-compose.yml` / `.dockerignore` | Docker 化：给别人在本机任意端口一键跑 |

## 已落地的知识库

1. **AI 软件测试**（第一个，batch-001 共 5 条）：B站「黑马 AI+软件测试」第 8 集被测项目分析 + 黑马头条实操笔记 + AI 测试概念全景 + 测试学习路线 + AI 生成用例趋势综述。

---

## 组件说明（前端 / 后端）

整个问答系统由 **4 个部分**组成，其中前 2 个在本仓库，后 2 个是运行期依赖：

### ① 前端 —— `web/static/index.html`（纯静态单页）
- 浏览器里打开的「对话框」：输入问题 → 调后端 `/api/ask` → 展示回答与引用片段；顶部徽标实时显示当前模式（RAG 生成式 / 语义检索 / 关键词检索）。
- 无任何外部 CDN/依赖，离线可用；已开 CORS，便于日后被其他页面 iframe / 接口对接。

### ② 后端 —— `web/server.py`（FastAPI，Python）
- 服务静态页面 + 两个核心接口：
  - `GET /api/status`：知识条目数、当前可用模式、嵌入/LLM 配置概要；
  - `POST /api/ask`：提问。按配置自动分级：嵌入+LLM 齐备 → **RAG 生成式回答（带引用）**；只有嵌入 → 语义片段；都没有 → 本地关键词检索。
- 直连 localbrain 引擎（同进程 import `kb.*`），不做中间件，零额外端口。
- 启动/停止脚本：`web/run.ps1`（Windows 本机）；Docker 见下节。

### ③ 引擎 —— localbrain（外部 Python 包 + 本地数据）
- 负责：入库收集（`localbrain collect file add`）、向量化（Chroma，bge-m3 嵌入）、检索与 RAG 组装（qwen 对话）。
- 数据目录 `~/.knowledge-base`、配置 `~/.localbrain/config.yaml`；配置里可切换 本地 Ollama / new-api / DashScope。
- 运维细节与踩坑记录见 `web/README.md`（chroma 只在收集时写入、qwen 思考模型需 `llm.think: false` 等）。

### ④ 模型服务 —— Ollama / new-api（运行期外部依赖，不在本仓库）
- 嵌入模型：`bge-m3`；对话模型：`qwen3.5:9b`（均需 Ollama 已拉取）。
- 端口：Ollama `11434`；new-api（可选统一网关）`3000`。

## 启动方法

### 方式 A：Windows 本机直接跑（当前开发方式）

```powershell
# 前置：已装 localbrain + Ollama(bge-m3/qwen3.5:9b)，配置见 web/README.md
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action start   # 启动
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action status  # 状态
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action logs    # 日志
powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action stop    # 停止
# 换端口：-Action start -Port 9000
```

### 方式 B：Docker 一键跑（给别人/其他机器，任意本地端口）

```bash
# 在仓库根目录（需要本机装 Docker，例如 WSL 内：wsl -e bash -c 'cd /mnt/d/ai/study_knowledge && ...'）
docker compose up --build -d                 # 默认 http://127.0.0.1:18765
KB_PORT=9000 docker compose up --build -d    # 换成本机 9000 端口
docker compose down                          # 停止
# 模型服务地址默认走 host.docker.internal:11434（宿主机 Ollama），可用环境变量覆盖，见 docker-compose.yml
```

> 提示：Docker 镜像只打包「前端 + 后端 + localbrain 引擎」，不打包你的个人内容与模型；
> 知识内容用 `./kb:/kb-in` 挂载导入（可选 `KB_IMPORT_DIR=/kb-in`），向量数据存具名卷 `kb-data`，换机器/别人跑互相隔离。

## 端口一览

| 端口 | 用途 | 绑定 |
| --- | --- | --- |
| `18765`（默认，可改） | 本仓库 Web 问答页（前端+后端一体） | `127.0.0.1`（Docker 内 `0.0.0.0`，由宿主端口映射对外） |
| `11201` | localbrain 自带 Web 管理界面（可选：`localbrain web`） | 127.0.0.1 |
| `11434` | Ollama（模型服务，运行期依赖，**不由本仓库启动**） | 本机 |
| `3000` | new-api（可选统一网关，运行期依赖，**不由本仓库启动**） | 本机（WSL2 转发） |

> 约定：本仓库启动的服务一律只绑 `127.0.0.1` + 非常用端口，不与 Docker/WSL 发布端口冲突（端口勘察记录见会话维护的 web/README 运维备忘）。

## 使用示例

打开 `http://127.0.0.1:18765`，在对话框输入，例如：

- 「什么是被测项目？测试前为什么要先熟悉被测项目的业务？」
- 「AI 辅助测试分哪几个阶段？和『针对 AI 的测试』有什么区别？」
- 「黑马头条这个被测项目里，测试设计是怎么开展的？」

回答基于知识库内容并附引用片段；未配置 AI 服务时自动降级为「关键词检索片段」。
