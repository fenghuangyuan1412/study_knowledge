# 变更日志

本项目按版本归档。`v1.0` 起，`main` 分支上的每个版本打一个 git tag。

---

## v1.0 — 知识库跑起来了（2026-09-16）

**这一版完成了三件事：知识库能跑、能调本地模型、能部署在虚拟机上对外服务。**

### 交付内容

| 能力 | 形态 |
| --- | --- |
| **知识库问答** | 两个独立知识库：AI 软件测试（10 条）、毛选（23 条）；RAG → 语义检索 → 关键词三级自动降级 |
| **本地模型** | 本地 Ollama（`bge-m3` 嵌入 + `qwen3.5:9b` 对话），**零云 API 依赖、零按量费用**；可一键切到 New API |
| **服务部署** | VMware 虚拟机（Ubuntu 24.04）上的 Docker 编排：`kb-web` + `nginx-proxy-manager`；宿主机只负责开穿透与提供模型 |
| **公网访问** | Tailscale Funnel 永久地址 `https://pc-202412121713.tail69ff66.ts.net/`；口令鉴权 + 按 IP 限流 + 并发闸门 |
| **开机自愈** | 两个 Windows 计划任务（登录时触发、隐藏窗口）：启动 VM → 端口转发 → 开穿透 → 校验守卫 |
| **手机端** | PWA，浏览器「添加到主屏幕」即全屏 App |
| **扩展位** | VM 内 NPM 占 80/443/81，后续别的网站与 new-api 直接往上放 |

### 知识内容

- `kb/ai-software-testing/`：batch-001（被测项目认知 + AI 测试全景）、batch-002（测试开发能力体系，参照华测《测试开发大师课》大纲）
- `kb/maoxuan/`：batch-001（五篇精读）、batch-002（第一卷全卷 18 篇内容总结，本地模型 map-reduce 生成）

### 工具链（都在 `web/`）

| 工具 | 作用 |
| --- | --- |
| `run.ps1` | 本机启停问答服务 |
| `deploy.ps1` | 一键恢复/状态/自启任务；`-Target host\|vm` 分流 |
| `vm.ps1` | VMware 虚拟机生命周期与开机自启 |
| `vm_ssh.py` / `vm_deploy.py` | SSH 一键部署到 VM（体检/上传/构建/启动/验证） |
| `kb_ingest.py` | 按知识库入库 Markdown（**不要用裸 `localbrain collect`**） |
| `mao_summarize.py` | 毛选分卷内容总结管线（map-reduce + 断点续跑） |
| `tunnel.ps1` | cloudflared 快速隧道（备用） |

### 修掉的真问题（都曾造成"静默错误"）

1. 并发触发 GPU `ROCm OOM` → localbrain **静默降级**为纯语义检索（接口正常、回答变片段）→ 加生成并发闸门 + `degraded` 标志
2. `FileCollector()` 输出目录**硬编码**，不读 config → DB 与文件落在不同库
3. localbrain 采集 id **秒级重复** → chunk 互相覆盖，18 篇只进 8 篇且**全程无报错**
4. `_index_content_for_search` 静默返回 False → "脚本全 OK、向量库只有一半"的假成功
5. 毛选长文 reduce 超上下文被**截断**（输出中途断掉）→ 改分层 reduce
6. 容器配置缺 `storage.persist_directory` → **问毛选返回软件测试内容**
7. 服务无口令启动却被隧道暴露到公网 → 隧道端加"守卫校验"，不通过就拒绝并停隧道
8. `python:3.12-slim` 不含 git → 原 Dockerfile 构建必失败

### 已知限制

- 机器必须开机并登录 Windows，服务才在线（当前按"登录后自动恢复"设计）
- 公网入口只有知识库这一个；NPM 尚未作为公网入口（需真实域名 + 端口映射 + 备案）
- 模型服务依赖宿主机（VM 通过 `192.168.163.1` 访问），宿主机与 VM 是绑定关系

---

## v1.0 之后 · 2026-09-18（安全修复 + 检索缓存自愈）

本次共三个提交：`c81eb91`（安全）、`f057aa1`（文档/约束）、`dd2ca73`（修复）。起因是把虚拟机里的文件传回本机时，顺带查出问答功能实际是坏的。

### 事件一：公开仓库里躺着一个 SSH 密码

`web/vm_ssh.py` 写的是 `os.environ.get("VM_PASS", "<口令字面量>")`。仓库在 GitHub 上是 **public**，所以这个默认值等于把虚拟机登录密码连密码 sudo 权限一起公开了，并且随 `6277c16` 永久留在 git 历史里——**删掉代码不等于修好**（值已失效，这里也不再复述）。

处理：代码改为只从环境变量或 `web/.runtime/vm.pass`（已 gitignore）取，取不到就报错退出（沉淀为 `agent.md` 第八节第 9 条）；VM 侧 `passwd awei` 换掉密码，旧值作废。

连带发现：`scp` 报 `REMOTE HOST IDENTIFICATION HAS CHANGED`。不是攻击——9/16 迁移过虚拟机，主机密钥真变了；而 `vm_ssh.py` 用的是 paramiko `AutoAddPolicy`，**根本不读 `known_hosts`**，所以变了也没人报警，本机 9/15 的旧记录一直烂在那儿。三方核对指纹确认身份后 `ssh-keygen -R` 清掉重钉。

> 另：`~/.ssh` 里当时只有 `known_hosts`，并没有私钥；到 `github.com` 的 22 端口不通。已生成 ed25519 密钥并在 `~/.ssh/config` 里把 `github.com` 指到 `ssh.github.com:443` 备用——**公钥尚未添加到 GitHub**，远程仍按原样走 HTTPS。

### 事件二：问答返回 `mode=none`，两个假设都是错的

现象：AI 软件测试库问什么都回"No relevant information was found"，毛选库正常。

- ❌ 假设一"`kb_import.py --skip-existing` 把向量挡在门外、向量缺失"——错。Chroma 的 `knowledge` collection 里 38 个 chunk，十个文件全覆盖。
- ❌ 假设二"`localbrain status` 显示 Doc Embeddings 只有 5，说明一半向量没进"——**指标看错了**。文档级向量和 RAG 检索无关，检索读的是 chunk 级 collection。`mine run`（5 → 10）是真实但无关的改进。
- ✅ 真因：`web/server.py` 的 `_rag_for()` 一旦建成 `RAGQuery` 就永久缓存，底层 Chroma `PersistentClient` 把 collection 视图缓在进程内存里。容器外进程写进去的数据，正在跑的服务看不见。

**定位手法（下次照抄）**：同一条查询走两条路径对比——容器内新起进程直调 `RAGQuery.query_with_fallback()`，与走 HTTP 调 `/api/ask`。本次前者 0.798 命中、后者 `mode=none`，即可断定故障在读取侧的缓存而非数据。`docker restart kb-web` 后立刻恢复，两库均回到 `mode=rag`、`degraded=false`（612 字/6 源、576 字/6 源）。

**根治（`dd2ca73`）**：缓存改为按磁盘指纹自愈——指纹 = 配置文件 + `db/metadata.db` + Chroma 目录顶层文件的 (mtime, size)，变了就换掉整个 `RAGQuery`；`*-shm` 排除（只读也会碰，否则无限重建）；`_cfg()` 一并按配置文件 mtime 重载。原"失败每 8s 重试"的节流不变。

### 运维口径（本次问到的三件事）

| 问题 | 答案 |
| --- | --- |
| 怎么启动 | 正常情况**不用管**：计划任务 `StudyKnowledge-VM-AutoStart` 开机起 VM，`StudyKnowledge-KB-AutoDeploy` 起 portproxy + Funnel 并做守卫校验。手工干预用 `web\deploy.ps1 -Action status` / `-Action ensure -Target vm`；虚拟机内改代码后 `docker compose -f docker-compose.vm.yml up -d --build kb-web` |
| 访问口令 | 存在**当前 Windows 用户的环境变量** `KB_ACCESS_TOKEN`（用户级，不入库、不进会话日志）。读取：`powershell -Command '[Environment]::GetEnvironmentVariable("KB_ACCESS_TOKEN","User")'` |
| 能不能用 nginx 改域名 | **不能**。`nginx-proxy-manager` 在隧道的**内侧**，公网地址由 Tailscale 边缘节点决定，证书也是它的。要换名字只有三条路：① `tailscale set --hostname=kb` 改 tailnet 内的机器名（Funnel 域名跟着变，之后要同步 `web/.runtime/public.url` 并重跑 `deploy.ps1 -Action ensure -Target vm`）；② 自建 Cloudflare **命名隧道**挂自己的域名；③ 公网 IP + 端口映射 + 备案（`web/deploy-vm/README.md` 已实测否决） |

### 本次遗留

- `dd2ca73` **只在代码里生效，线上容器仍是旧镜像**——要 `docker compose build kb-web` 才算真修好（尚未验证真实链路）。
- `web/docker/kb_import.py` 用裸 `localbrain collect file add --skip-existing`，违反第八节第 3 条，且 `entrypoint.sh` 每次启动都跑、不等模型就绪、导入失败也不返回非零码。这次不是它引起的，但它是个定时炸弹。
- `vm_ssh.py put` 上传到远端 `/tmp` 会抛 paramiko `FileNotFoundError`（相对/绝对路径都试过），原因未查，本次靠 base64 绕过。
- 推送对 `github.com:443` 会**间歇性超时**（本次连续 4 次失败、第 5 次成功），与 `agent.md` 第八节「环境依赖」里记的 hosts 指向 `140.82.113.3` 有关；失败就重试，不是权限问题。
- 排查期间在 `web/.runtime/`（已 gitignore）留了几个一次性脚本：`kb_verify.py` `kb_probe.py` `kcol.py` `kq.py` `kr.py` `test_cache_stamp.py`，可删。
- 跨会话交接：`three_think`（3D 桌游《马尼拉》，`D:\ai\game_self\three_think`）的资料已发给另一个 Qoder 会话继续做联机；本仓库的 `windows-handoff.md` 通道还在虚拟机 `/home/awei/` 下未拉回本机。

---

## 后续规划（v1.1+ 候选）

按优先级排列，尚未排期：

### 1. 界面优化
- 问答页交互与视觉打磨（当前是可用但朴素的状态）
- 引用片段的展示更好用：按来源折叠、点击跳原文、显示卷/篇层级
- 会话历史与多轮上下文（后端 `query.rag.conversation` 已具备能力，前端未接）
- 移动端细节：长回答的阅读体验、输入区键盘处理

### 2. 知识内容可添加（**朋友也能加**）
- **Web 端上传入口**：页面上直接传 Markdown / PDF → 后端入库 → 自动向量化
- **PDF 解析入向量库**：localbrain 已支持 PDF（`FileCollector` + `PyPDF2`，含按页切分），需要把它接到 Web 层并做进度反馈
- **权限分级**：朋友只能"投稿"，不能删除或覆盖既有知识；投稿进待审区，本人确认后才入库
- **向量化任务队列**：入库+嵌入是耗时操作，需要异步任务与进度提示（现在是命令行同步执行）
- 复用 `web/kb_ingest.py` 的踩坑规避逻辑（唯一 id、检查索引返回值、显式 output_dir）

### 3. 其他
- 安卓端（复用 `/api/status` 与 `/api/ask`，口令走 `X-KB-Token` 头）
- 毛选后续卷（`mao_summarize.py --volume 2..7`）
- NPM 作为真正公网入口（需要域名 + 端口映射 + 备案，成本较高）
