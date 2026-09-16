# 个人学习知识库

> **当前版本：v1.0**（2026-09-16）——知识库运行、本地模型接入、虚拟机部署服务三项已完成。
> 版本记录与后续规划见 [`CHANGELOG.md`](CHANGELOG.md)；方向约定见 [`agent.md`](agent.md)。

个人学习知识库：把学习内容按知识库组织并沉淀为 Markdown，再向量化成本地可检索、可问答的知识库。每条内容尽量带出处；配合「可溯源检索」能力，引用可回原文核对。项目本地优先、离线可用，面向本人使用，也便于打包分享给他人自部署。

## 知识库

| 知识库 | 一句话简介 | 状态 |
| --- | --- | --- |
| AI 软件测试（`kb/ai-software-testing`） | 用 AI 能力加速传统软件测试：被测项目认知、AI 辅助用例设计、Agent 测试等 | ✅ 已接入 |
| 毛选（`kb/maoxuan`） | 两层能力：经典篇目「要点+解读」研读问答 + 《毛选》1–7 卷全文本地检索与段落溯源 | ✅ 已接入 |

> 每个知识库在自己的目录里放一篇 README，写明该库的简介、内容组织与用法/学习路线。

## 组件

1. **内容层** —— Markdown 文本，按库组织，经 git 版本管理，是知识的唯一事实来源。
2. **向量引擎 localbrain** —— 外部 Python 包：`collect` 原文入库、`mine` 向量化（Chroma + bge-m3 嵌入）、检索与 RAG 组装；每个知识库一份独立数据实例；模型后端可切换（本地 Ollama / OpenAI 兼容网关 / 云 API）。
3. **Web 问答层** —— 静态单页 + FastAPI 后端：提问按配置自动分级（RAG 生成式 → 语义检索 → 关键词检索），无远端服务也可用；支持 Docker 容器化，任意机器、任意本地端口一键运行。
4. **Skill 层（agent 知识处理能力）**：
   - `mao-selected-works`：全文语料建索引与检索（SQLite FTS5，可选 bge-m3 向量 + 重排的混合检索）；
   - `wenshu`（文枢）：文献导入、段落级锚点、引文格式化、理论谱系、检索问答——可溯源、不编造。
5. **模型服务（运行期外部依赖）** —— 嵌入（bge-m3）与对话（qwen 等）模型，Ollama / new-api 均可承载。

## 部署

1. **准备**：Python 3.10+；安装 localbrain 与所需模型/API key；所需 skill 文件夹放入所用 agent 工具的 skills 目录（刷新 / 重启后生效）。
2. **全文检索库（大语料，如毛选 1–7 卷）**：进入对应 skill 目录执行
   `python scripts/build_index.py` 建索引；随后 `python scripts/search.py catalog --volume 第一卷`、`search "关键词"`、`show --title 篇名` 检索；
   需要语义检索时 `python scripts/config.py set rag.enabled true`（API key 走环境变量，如 `MAO_SKILL_API_KEY`）。
3. **知识入库（向量问答）**：把整理好的 Markdown 用 `localbrain collect file add` 收进对应知识库，再 `localbrain mine` 完成向量化。
4. **启动 Web 问答**：
   - 本机：`powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action start`（start / status / logs / stop，可 `-Port` 换端口）；
   - Docker：`docker compose up --build -d`（默认 http://127.0.0.1:18765，`KB_PORT=9000` 可换端口；镜像只打包应用与引擎，个人内容与模型数据用卷挂载，互不混入）。
5. **新增知识库**：建目录 + 写 README 简介；语料按需走「全文索引」或「向量入库」任意一种接入。
6. **长期部署（虚拟机 Docker + 隧道穿透，供朋友内测）**：知识库跑在 **VMware 虚拟机（Ubuntu 24.04）的 Docker 里**作为长期服务器，宿主机只负责「开穿透」与「提供模型服务」。数据与模型都不出本机。
   - **永久地址**：`https://pc-202412121713.tail69ff66.ts.net/`（Tailscale Funnel，**不随重启变化**）。Tailscale 在宿主机、Funnel 只能转发宿主机端口，因此用 `netsh portproxy` 把 18765 转给 VM —— **公网地址与口令始终不变**；
   - **开机即在线**：两个 Windows 计划任务在**登录时**自动拉起（均隐藏窗口、不重复触发）：
     `StudyKnowledge-VM-AutoStart`（`vmrun` 启动虚拟机）→ `StudyKnowledge-KB-AutoDeploy`（停宿主服务 → 等 VM → 端口转发 → 开 Funnel → 校验守卫）。VM 内 Docker 与容器都是自启/自愈的；
   - **一键恢复**：`web\deploy.ps1 -Action ensure -Target vm`；状态查询 `web\deploy.ps1 -Action status`、`web\vm.ps1 -Action status`；
   - **访问口令（强制）**：`KB_ACCESS_TOKEN`（VM 的 `.env` 与宿主机环境变量同值，**不入库**）。**没设口令时会拒绝暴露**，并端到端确认「无口令请求返回 401」；
   - **一键部署/更新**：`python web\vm_deploy.py --stage all`；改完 `web/` 代码后 `--stage upload` + `build` + `up` 即可；
   - 把「地址 + 口令」发给朋友即可；手机端浏览器打开后「添加到主屏幕」即成为全屏 App（PWA）；写**安卓端**直接复用 `/api/status` 与 `/api/ask`（鉴权走 `X-KB-Token` 头），**不需要另建后端**；
   - **扩展位（后门）**：VM 里的 `nginx-proxy-manager` 占 80/443/81，以后加站点、申请证书在网页上点几下即可；**别的网站与 new-api 都往这里放**；
   - **上云**：`Dockerfile` + `docker-compose.yml` 已含全部环境变量，可直接用于云服务器或宝塔面板；
   - 虚拟机部署细节见 `web/deploy-vm/README.md`，环境变量与踩坑记录见 `web/README.md`，方向约定见 `agent.md` 第六节。

## 使用示例

- Web 问答页：打开本地地址，提问如「AI 辅助测试分哪几个阶段？」；回答附知识库引用片段，未配置 AI 服务时自动降级为关键词检索。
- 全文检索（毛选原文定位）：`python scripts/search.py search "实事求是"` —— 返回命中篇目、段落与出处（卷-篇），可继续 `show --title 篇名` 回看全文核对。

## 内容约定

- **方向性 / 结构性改动**（前后端、切换知识库方向——如软件测试、模型微调等）在 `agent.md` 约定后执行；具体内容增改直接改对应知识库的 Markdown。
- **公网只暴露 Web 问答层**：毛选 1–7 卷全文只在本机 skill 目录，**不在公网链路上**（Web 层的毛选库只有 5 篇精读笔记）；日后新增含版权大语料的库，默认不纳入公网问答。
- 版权文本、大语料与向量/索引数据留在本机，不入版本库。
