# Agent.md — 个人学习知识库 · 主控文件

> 本文件是项目的「方向控制台」：涉及**大方向、结构性改动**的需求，一律先修订本文件，
> 再据此执行具体的知识库搭建 / 内容增改任务。

---

## 一、项目定位

这是一个**个人专用学习知识库**（账号：fenghuangyuan1412）：

- 把「我当前要学习的内容」集中放进这个库里，边学边沉淀；
- 知识库按学习主题 / 方向组织，不同阶段可以承载不同的学习内容；
- 沉淀后的内容会向量化，供**本地 Web 问答页**直接检索问答，日常提问不再依赖 agent 手工操作。

## 二、运行与构成

- **向量引擎：localbrain**（`localbrain` / `kb` 命令）
  - 数据目录：`~/.knowledge-base`（**不纳入 git**，含 1_collect 原文 / db 元数据与 Chroma 向量库）
  - 配置文件：`~/.localbrain/config.yaml`（**不纳入 git**，可切换后端：阿里云 DashScope 免费额度 / 本地 new-api(Ollama, OpenAI 兼容)）
- **内容载体**：仓库内 `kb/<方向>/batch-<编号>/items/*.md`（UTF-8 Markdown），一份内容 = 一条知识
  - 每次向知识库添加内容：**先把 md 提交进 git 分支，再把同一份 md `localbrain collect file add` 收进向量库**
- **Web 问答页**：`web/`（main 分支维护），后端优先 RAG（大模型作答），降级为语义检索 / 关键词检索
- **Skill 层（agent 知识处理能力）**：`mao-selected-works`（全文建索引与检索：SQLite FTS5，可选 bge-m3 向量 + 重排混合检索）、`wenshu` 文枢（文献导入 / 段落锚点 / 引文格式化 / 谱系图谱 / 检索问答，可溯源不编造）；语料与索引存放于本地 agent skills 目录（**不入 git**），毛选用法见 `kb/maoxuan/README.md`
- **大方向改动**（统一在 `agent.md` 中维护）：前端 / 后端改动；切换不同知识库方向（软件测试、模型微调等）

## 三、文件约定

| 文件 / 层级 | 作用 | 何时修改 |
| --- | --- | --- |
| `agent.md`（本文件） | 方向、结构、运行机制、git 工作流的总控 | 需要大方向改动时（前后端、更换学习方向/知识库等） |
| `README.md` | **只写项目介绍**（是什么、含哪些库、主要特性、文档导航） | 项目定位或知识库清单变化时同步 |
| `CHANGELOG.md` | 版本记录与后续规划；每个版本在 `main` 上打 git tag | 每次归档版本时 |
| `web/` | Web 问答页与全部部署运维工具（服务 / 脚本 / 文档） | 结构 / 前端 / 后端 / 部署改动时（main） |
| `web/README.md` | 运行前提、启停、环境变量、知识入库、踩坑记录 | 运维方式变化时同步 |
| `web/deploy-vm/README.md` | 虚拟机部署架构、一键部署、反向代理用法 | 部署形态变化时同步 |
| `kb/<方向>/batch-<编号>/items/*.md` | 具体学习内容（每个方向一个库） | 日常创建知识库、增删改学习内容时（**一律在分支上**） |

**文档分工原则**：根 `README.md` **只放介绍**，安装/部署/运维等操作细节一律放在对应目录的 `README.md` 里，避免根文件越来越长。

**新增一个知识库**：建 `kb/<方向>/` 目录 + 写该库的 `README.md`（简介、批次索引、学习路线）；
再在 `web/server.py` 的 `PROFILES` 里登记一份独立配置与数据目录，语料按「向量入库」（`web/kb_ingest.py`）或「全文索引」接入。

## 四、git 工作流约定（重要）

**目的：保证 main 主枝稳定 —— 别人/其他并发上传不影响 main；合入前必须人工同意。**

1. **main 分支**：只承载结构文件（README / agent.md / 规划 md）与 `web/` 问答页。知识内容**不直接提交 main**。
2. 任何**知识库内容添加 / 修改**（每个方向的知识 md）：
   - 从最新 main 切出分支，命名：`kb/<方向>/batch-<编号>`（如 `kb/ai-software-testing/batch-001`）；
   - 在该分支上增改 `kb/<方向>/batch-<编号>/items/*.md`；
   - **每批固定 5 条**（5 篇网页/视频知识整理），一次提交；
   - 提交信息用中文并写明上传介绍，格式：`知识库：<方向> 第<N>批（5条）—— 条目列表/一句话介绍`；
   - 分支上的内容**同时** `localbrain collect file add` 收入向量库（保持 git 与向量库同源）。
3. 分支完成后**提请仓库主人（用户）同意**，得到确认后才 merge 回 main，并自动 `git push origin`。
4. 历史批次如需修改：同样开分支 → 改 → 提请同意 → 合入。

## 五、向量化与问答链路

- 收集：`localbrain collect file add <kb 内 md>` → 原文进入 `~/.knowledge-base/1_collect`
- 向量化（需嵌入服务，先配 DashScope 免费额度，可切 new-api/Ollama）：`localbrain mine`（生成 chunk + Chroma 向量）
- 问答：`web/` 页面提问 → 后端三级降级：RAG（嵌入+LLM）→ 语义检索（仅嵌入）→ 关键词检索（无需服务）
- 日常用户提问走 `web/` 问答页，无需 agent 介入

## 六、公网访问与常态化部署（方案 A：隧道穿透）

**定位**：本知识库只有两个用途 —— 本人自用 + 朋友帮忙内测（不盈利、不对外运营）。因此选**隧道穿透**而非云服务器：不迁移数据、不另外部署模型，直接把自己电脑上已跑通的服务安全映射到公网。

- **链路（当前）**：`Tailscale Funnel` → 宿主机 `127.0.0.1:18765` → `netsh portproxy` → **VM `192.168.163.128:18765`（Docker 容器 `kb-web`）** → 宿主机 Ollama（`bge-m3` + `qwen3.5:9b`）
- **宿主形态**：知识库**跑在 VMware 虚拟机（Ubuntu 24.04）的 Docker 里**，目录 `/opt/study-knowledge`。宿主机只负责两件事——**开穿透**与**提供模型服务**。这样 VM 就是一台可长期使用的服务器，后续别的站点也往上面放。
- **永久地址**：`https://pc-202412121713.tail69ff66.ts.net/`。Tailscale 跑在宿主机、Funnel 只能转发宿主机本地端口，所以用 portproxy 把 18765 转给 VM——**对 Tailscale 而言后端没变，公网地址与口令都不需要改**。
- **模型**：保持**本地自托管**，不引入云 API、无按量费用；代价是本机需保持开机。
- **访问控制（强制）**：服务一经隧道暴露，**必须**带访问口令。口令从环境变量 `KB_ACCESS_TOKEN` 注入，**任何情况下不写入入库文件**。
  - 前端：首次访问提示输入口令 → 存 `localStorage` → 请求以 `X-KB-Token` 头携带；
  - 后端：`web/server.py` 中间件校验，并**按 IP 限流**，防止口令外泄后刷爆本机模型；
  - **暴露前必须端到端验证**：不带口令请求 `/api/status` 必须得到 401。若返回 200，说明服务是以「无口令模式」启动的，此时**禁止开隧道**（`deploy.ps1` / `tunnel.ps1` 会自动拒绝并停掉隧道）。
- **并发保护（强制）**：本机显存有限（AMD 16GB），**必须**保留生成并发闸门（`KB_MAX_CONCURRENT`）。并发压垮 GPU 会触发 ROCm OOM，localbrain 会静默降级成「纯语义检索」——接口看起来正常，但用户拿到的是片段列表而非 AI 回答。
- **常态化（开机即在线）**：整条链由两个 Windows 计划任务在**登录时**自动拉起（都隐藏窗口、不重复触发）：
  - `StudyKnowledge-VM-AutoStart` → `vm.ps1 -Action start`（`vmrun start <vmx> nogui` 启动虚拟机）；
  - `StudyKnowledge-KB-AutoDeploy` → `deploy.ps1 -Action ensure -Target vm`（停宿主服务 → 等 VM → 端口转发 → 开 Funnel → 校验守卫），以 `-RunLevel Highest` 运行（`netsh portproxy` 需要管理员）。
  - VM 内 Docker 是 `systemctl enable`，容器是 `restart: unless-stopped`，所以 VM 一启动容器就起。手动排查用 `deploy.ps1 -Action status` / `vm.ps1 -Action status`。
- **对外范围**：口令即边界。两个库（`ai-software-testing`、`毛选`）都对内测朋友开放；**Web 层的毛选库只有「精读笔记 + 分卷内容总结」，1–7 卷原文全文不在公网链路上**（全文只在本地 skill 目录）。日后新增知识库若含版权大语料，**默认不纳入公网问答**。
- **移动端**：问答页按 PWA 适配，手机浏览器「添加到主屏幕」即可当 App 用；**API 口径需保持可被安卓端复用**——口令统一走 `X-KB-Token` 头，后续安卓端直接调 `/api/status` 与 `/api/ask`，不另建后端。
- **扩展位（后门，已预留）**：VM 里的 `nginx-proxy-manager` 占 80/443/81，以后加站点在网页上点几下即可（含自动证书）；加新端口就在宿主机补一条 portproxy。**别的网站与 new-api 穿透都往这两个位置放**，不需要改动本知识库的链路。详见 `web/deploy-vm/README.md`。
- **上云预案**：`Dockerfile` + `docker-compose.yml` 已支持容器化（含口令/限流/并发闸门等全部环境变量），可直接用于云服务器或宝塔面板；详见 `web/README.md`。
- **本项目的自研工具（都在 `web/`，需入库维护）**：
  - `deploy.ps1` —— 公网部署的一键恢复/状态/自启任务管理；`-Target host`（服务在本机）或 `-Target vm`（服务在 VM，含端口转发）；`-IntervalMinutes 0` 表示只登录时跑一次、不重复弹窗；
  - `vm.ps1` —— VMware 虚拟机生命周期（start/stop/status/wait-ssh）与自启任务；
  - `vm_ssh.py` / `vm_deploy.py` —— 通过 SSH 把应用与数据部署进 VM（体检/上传/生成 .env/构建/启动/验证）；
  - `deploy-vm/` —— VM 的编排（`docker-compose.vm.yml`）、Docker 引导脚本与部署文档；
  - `tunnel.ps1` —— cloudflared 快速隧道（备用方案）；
  - `kb_ingest.py` —— 按指定知识库入库 Markdown。**必须用它而不是裸 `localbrain collect`**：CLI 的 config 是硬编码的，且采集输出目录不读 config、秒级 id 会互相覆盖（详见 `web/README.md` 踩坑 13-16）；
  - `mao_summarize.py` —— 毛选分卷内容总结管线（map-reduce + 断点续跑），`--volume N` 依次产出后续批次。

**内容批次例外**：分卷整理（如毛选全卷内容总结）**以「一卷」为批次单位**，不受第四节「每批固定 5 条」约束——自然的卷边界优于固定条数。

## 七、第一个知识库：AI 软件测试

- 学习目标：利用 AI 能力对传统软件测试进行更快节奏的测试（含被测项目认知、AI 辅助用例设计、Agent/智能体测试等）
- 学习素材源：B 站「黑马测试 AI+软件测试第一篇（测试基础+AI手工测试，200 集）」+ 配套公开笔记 + 权威网页资料
- 学习内容按批次沉淀于 `kb/ai-software-testing/batch-*/items/`

---

## 八、关键约束与踩坑速查（v1.0 定型）

以下是**结构性约束**，违反任意一条都会导致线上出问题。完整复现与排查过程见 `web/README.md` 踩坑记录（共 22 条）。

### 硬约束（必须遵守）

1. **口令**：服务一经暴露，`KB_ACCESS_TOKEN` 必填，且**绝不写入任何入库文件**；暴露前必须确认「无口令请求 `/api/status` 返回 401」。
2. **并发闸门**：`KB_MAX_CONCURRENT` 必须保留（默认 2）。本机 AMD 16GB 显存，并发会触发 `ROCm error: out of memory`，localbrain 随即**静默降级**为纯语义检索——接口看着正常，用户拿到的却是片段列表而非 AI 回答。
3. **入库必须用 `web/kb_ingest.py`**，不要用裸 `localbrain collect`（理由见下表前三条）。
4. **批量生成内容与批量入库不要并发**（争抢显存会让 embedding 失败）。
5. **两个知识库是两个独立数据实例**：任何容器化 / 迁移 / 备份都要同时处理 `config.yaml` 与 `config-maoxuan.yaml`，缺一个就有一个库哑掉。
6. **`.ps1` 里代码字符串只用 ASCII**：Windows PowerShell 5.1 在无 BOM 时按 GBK 读脚本，中文字符串会变乱码并破坏语法（注释可中文，代码字符串不行）。
7. **不要用管道调用 `run.ps1` / `deploy.ps1` / `tunnel.ps1` / `vm.ps1`**：它们 `Start-Process` 起的常驻进程会继承标准输出句柄，管道永不关闭，调用方会一直等下去。自动化请用 `Start-Process ... -RedirectStandardOutput <文件>`。
8. **PowerShell 变量名大小写不敏感**：`$target` 与 `$Target` 是同一个变量，改名时要全局搜。

### localbrain 的坑（这四条都造成过"静默错误"——脚本报成功、实际没生效）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 入库显示 18/18 全部 OK，向量库里只有一半 | 采集 id 是**秒级**的（`file_YYYYmmdd_HHMMSS`），同一秒采集的多个文件 id 相同 → chunk id 互相覆盖 | `kb_ingest.py` 检测到撞 id 时删掉重采（等 1.1 秒） |
| 脚本报成功但检索不到 | `_index_content_for_search` 内部 `except` 后 `return False`，chunker 失败时甚至**不打日志直接 return** | **必须检查它的返回值**才算真成功 |
| DB 在 A 库、文件却落在 B 库 | `FileCollector()` 无参构造时输出目录**硬编码** `~/.knowledge-base/1_collect`，不读 config（而 sqlite/Chroma 会读） | 显式传 `output_dir` |
| **问毛选却返回软件测试的内容** | 容器配置只写了 embedding/llm/data_dir，缺 `storage.persist_directory` → 检索落到默认库的向量目录 | 以**宿主机完整配置为模板**，只覆盖 `data_dir`/`storage.persist_directory`/`embedding`/`llm` |

### 环境依赖（易踩）

- `python:3.12-slim` **不含 git**，而 `pip install "localbrain @ git+https://…"` 需要它 —— 缺了直接构建失败；
- VM 只能直连 `download.docker.com` 与国内镜像；**`pypi.org`、`registry-1.docker.io`、`github.com` 均不通** → 必须配 `PIP_INDEX` / `GITHUB_PROXY` / docker `registry-mirrors`；
- `netsh interface portproxy` 需要管理员权限（对应计划任务用 `-RunLevel Highest` 注册，不弹 UAC）；
- `github.com` 域名当前被阻断（解析到的 IP 不通，其他 GitHub IP 正常），宿主 hosts 里已指向可达 IP `140.82.113.3`；换网络后若拉取失败先检查这一行。

---

## 九、变更记录

- **第一次提交（信息：agent修改）**：创建本文件，确立「agent.md 管方向 + 主题 md 管内容」的知识库工作方式。
- **第二次提交（信息：结构-接入 localbrain 向量库与 Web 问答页，确立 git 分支合流工作流）**：接入 localbrain 向量引擎；确立 `kb/<方向>/batch-*/items` 内容目录与「分支添加 → 同意后合入 main → 推送 origin」工作流；新增 `web/` 本地问答页；沉淀第一批 AI 软件测试知识。
- **本次提交（信息：接入毛选全文检索与文枢溯源 skill，README 改为可分享版本）**：DSH 本机接入 `mao-selected-works` 与 `wenshu` 两个 skill，毛选 1–7 卷全文语料/索引进本机 skills 目录（不入 git），`kb/maoxuan/README.md` 补齐「全文语料与可溯源检索」用法；`README.md` 去除本地结构细节，改为面向分享的项目说明（组件 / 部署更详细）。
- **本次提交（信息：结构-确立公网访问方案 A（隧道穿透）与访问口令约定）**：新增第六节，明确以 `cloudflared` 隧道把本机服务映射公网、模型保持本地自托管；立「口令从 `KB_ACCESS_TOKEN` 注入、绝不入库」与「按 IP 限流」两条强制约定；确认毛选全文不在公网链路、Web 层仅 5 篇精读笔记；问答页适配 PWA 供手机使用，API 口径统一为 `X-KB-Token` 头以便日后安卓端复用。
- **本次提交（信息：结构-公网访问升级为常态化部署（Tailscale Funnel + 开机自启），并新增内容两批）**：
  1. **隧道换为 Tailscale Funnel**，拿到永久固定地址 `https://pc-202412121713.tail69ff66.ts.net/`（快速隧道地址每次重启都会变，降级为备用）；新增 `web/deploy.ps1`（幂等一键恢复 + 守卫校验 + 状态查询）与 Windows 计划任务 `StudyKnowledge-KB-AutoDeploy`（登录时 + 每 5 分钟），实现**重启后自动恢复、隧道掉线自动重拉**。
  2. 立第三条强制约定：**必须保留生成并发闸门**（并发会触发 ROCm OOM 并导致静默降级）；暴露前必须端到端确认「无口令返回 401」。
  3. 立**内容批次例外**：分卷整理以「一卷」为批次单位，不受「每批固定 5 条」约束。
  4. 内容两批：`kb/ai-software-testing/batch-002`（参照华测《测试开发大师课》大纲，5 条测试开发能力体系）；`kb/maoxuan/batch-002`（第一卷全卷 18 篇内容总结，用本地模型 map-reduce 生成，解决向量库内容过薄、本地模型只能给大纲的问题）。
- **本次提交（信息：结构-知识库迁入虚拟机长期部署，穿透链与扩展位改造）**：
  1. **宿主形态变更**：知识库从「跑在 Windows 宿主上」迁到 **VMware 虚拟机（Ubuntu 24.04）的 Docker**（`/opt/study-knowledge`）。宿主机保留两个职责——开穿透、提供模型服务。公网地址与口令**均未变化**（portproxy 把 18765 转发给 VM，对 Tailscale 而言后端没变）。
  2. 新增 `web/deploy-vm/`（编排 + Docker 引导 + 部署文档）、`web/vm.ps1`（VM 生命周期与自启任务）、`web/vm_ssh.py`、`web/vm_deploy.py`（SSH 一键部署）；`deploy.ps1` 新增 `-Target vm` 与 `-Target host` 分流，并把计划任务从「每 5 分钟重复」改为**仅登录时执行且隐藏窗口**（用户反馈弹窗打断操作）。
  3. **容器多知识库支持**：`bootstrap_config.py` 现在生成两个库的配置，并**以宿主机完整配置为模板**（挂载 `/config-templates`）——只覆盖 `data_dir`/`storage.persist_directory`/`embedding`/`llm`，避免缺 `storage` 段导致跨库串味。
  4. Dockerfile 补 `git`（原版缺，构建必失败）并加 `DEBIAN_MIRROR`/`PIP_INDEX`/`GITHUB_PROXY` 构建参数适配国内网络。
  5. **扩展位（后门）**：VM 内 `nginx-proxy-manager` 占 80/443/81，后续别的网站与 new-api 穿透直接往这里放。踩坑记录补至 22 条。
- **v1.0 归档（信息：归档 v1.0——知识库运行 + 本地模型 + 虚拟机部署三项完成）**：
  1. 新增第八节「关键约束与踩坑速查」，把 8 条硬约束与 localbrain 的四个"静默错误"固化为项目级约定；
  2. 新增 `CHANGELOG.md`，确立「按版本归档、`main` 上打 git tag」的做法，本版打 tag `v1.0`；
  3. `web/deploy-vm/README.md` 补齐 **Nginx Proxy Manager 完整用法**，并记录了「自建域名访问不了」的实测结论与四种场景的正确做法；
  4. **记录后续方向**：① 界面优化（交互/引用展示/多轮上下文）；② 知识内容可由朋友添加（Web 上传入口、PDF 解析入向量库、投稿待审、异步任务队列）；③ 安卓端、毛选后续卷、NPM 作为公网入口。
