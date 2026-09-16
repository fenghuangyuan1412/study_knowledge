# 本地知识库 Web 问答页（web/）

在浏览器里直接向知识库提问的后端与页面（main 分支维护）。
**本文覆盖：运行前提、启停、后端能力与切换、知识入库、环境变量、公网访问、云/虚拟机部署、踩坑记录。**

> 项目整体介绍见仓库根目录 [`README.md`](../README.md)；虚拟机部署细节见 [`deploy-vm/README.md`](deploy-vm/README.md)；
> 方向约定见 [`agent.md`](../agent.md)。

> ⚠️ **给自己的提醒（重要）**：先用阿里云 DashScope 免费额度把整库与问答跑通；免费额度用完 / 想完全本地化后，
> **切换成本地模型**——把 `~/.localbrain/config.yaml` 的 `embedding`/`llm` 两段改成走本地 **new-api（OpenAI 兼容）接 Ollama**
> （改 provider/model/api_key/base_url 四字段，重启服务即可，页面状态栏会自动切换模式）。本仓库所有文件不含任何 key。


## 运行前提

1. **Python 3.10+**（容器方案无需本机 Python）；
2. localbrain 已安装并初始化（数据在 `~/.knowledge-base`，配置 `~/.localbrain/config.yaml`）；
3. 模型服务可达：默认走本机 Ollama（`127.0.0.1:11434`，需有 `bge-m3` 与对话模型），或任一 OpenAI 兼容网关；
4. 知识内容已入库（见下节）。

## 知识入库（新增 / 更新内容）

**入口**：把整理好的 Markdown 放进 `kb/<方向>/batch-<编号>/items/`，然后执行：

```powershell
# 按知识库入库（会自动采集 + 写 Chroma 向量）
python web\kb_ingest.py --kb ai-software-testing --glob "kb/ai-software-testing/batch-003/items/*.md"
python web\kb_ingest.py --kb maoxuan           --glob "kb/maoxuan/batch-003/items/*.md"

# 预览不落库
python web\kb_ingest.py --kb maoxuan --glob "..." --dry-run
```

> ⚠️ **必须用 `web/kb_ingest.py`，不要直接用裸 `localbrain collect`**。原因（详见踩坑 13–15）：
> CLI 的配置路径是硬编码的、文件输出目录不读配置、且采集 id 是秒级的（同秒采集会互相覆盖）。
> `kb_ingest.py` 这三件事都处理了，并会**检查索引返回值**，避免"脚本报成功、向量库没进"。

**部署在虚拟机上时**，入库后要把数据同步过去：

```powershell
python web\vm_deploy.py --stage upload   # 上传应用 + 两个库的数据
python web\vm_deploy.py --stage up       # 重建容器使其生效
```

**全文检索库（大语料，如《毛选》1–7 卷）**独立于向量库，走 skill 建索引，用法见
[`kb/maoxuan/README.md`](../kb/maoxuan/README.md)。

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


---

## 公网访问（方案 A：隧道穿透 + 常态化部署）

定位：**本人自用 + 朋友内测**。不迁移数据、不部署云模型——把自己电脑上已跑通的服务映射到公网，Ollama 仍然只在本机跑。方向约定见仓库根目录 `agent.md` 第六节。

- **当前接线**：Tailscale Funnel → 本机 `127.0.0.1:18765`
- **永久地址**：`https://pc-202412121713.tail69ff66.ts.net/`（**固定域名，不随重启变化**）

### 一次性准备

```powershell
# 1) 设访问口令（持久化到用户环境变量，绝不入库）
$alphabet='abcdefghijkmnpqrstuvwxyz23456789'
$rng=New-Object System.Security.Cryptography.RNGCryptoServiceProvider
$b=New-Object byte[] 14; $rng.GetBytes($b)
$token=-join ($b | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
[Environment]::SetEnvironmentVariable('KB_ACCESS_TOKEN',$token,'User')
$token   # 记下来，发给朋友

# 2) 装 Tailscale（本机没有 winget，用 MSI 静默装）
#    下载 https://pkgs.tailscale.com/stable/tailscale-setup-1.102.4-amd64.msi
#    msiexec /i tailscale-setup-1.102.4-amd64.msi /qn /norestart
#    装完服务自动启动且开机自启；再登录一次（会弹浏览器）：
& "C:\Program Files\Tailscale\tailscale.exe" up

# 3) 开 Funnel（**首次必须由账号主人**在浏览器点一次授权，链接由命令打印）
& "C:\Program Files\Tailscale\tailscale.exe" funnel --bg --yes 18765

# 4) 注册开机自启 + 看门狗
powershell -ExecutionPolicy Bypass -File web\deploy.ps1 -Action install-task
```

### 日常使用

| 命令 | 作用 |
| --- | --- |
| `web\deploy.ps1 -Action ensure` | **幂等一键恢复**：起服务 → 开隧道 → 校验守卫 → 记录地址（计划任务每 5 分钟自动跑） |
| `web\deploy.ps1 -Action status` | 一眼看清 服务 / 守卫 / 隧道 / 公网地址 / 计划任务 状态 |
| `web\deploy.ps1 -Action url` | 只输出公网地址（供脚本取用） |
| `web\deploy.ps1 -Action stop` | 停隧道（公网立刻不可达，本机服务继续跑） |
| `web\deploy.ps1 -Action install-task` | 注册计划任务：登录时 + 每 5 分钟自动 `ensure` |
| `web\deploy.ps1 -Action uninstall-task` | 移除计划任务 |
| `web\run.ps1 -Action start\|stop\|status\|logs` | 只管本机服务 |
| `web\tunnel.ps1 -Action start\|stop\|status\|url\|logs` | 备用：cloudflared 快速隧道（地址每次重启会变） |

**开机自启是怎么实现的**：Tailscale 本身是 Windows 服务（`StartType=Automatic`），开机即连；计划任务 `StudyKnowledge-KB-AutoDeploy` 在**登录时**和**每 5 分钟**执行 `deploy.ps1 -Action ensure`。所以无论重启还是隧道掉线，最多 5 分钟自动恢复。实测从「服务+tunnel 全停」到完全恢复约 **10 秒**。

### 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `KB_ACCESS_TOKEN` | 空 | **上线必设**。访问口令；多个用英文逗号分隔（可给每个朋友一个，事后单独作废） |
| `KB_RATE_LIMIT` | 60 | 每 IP 每分钟 `/api/ask` 上限 |
| `KB_AUTH_FAIL_LIMIT` | 10 | 每 IP 每分钟口令试错上限（防爆破） |
| `KB_MAX_CONCURRENT` | 2 | 同时进行的模型生成数（**显存保护**，见踩坑 4） |
| `KB_QUEUE_TIMEOUT` | 180 | 排队等待上限（秒），超时返回 503 |
| `KB_CORS_ORIGINS` | 空 | 默认不开放跨域；填白名单（逗号分隔）才放行 |
| `KB_TRUST_PROXY` | 1 | 经隧道/反代时从 `CF-Connecting-IP` / `X-Forwarded-For` 取真实客户端 IP |

### 手机端

- 手机浏览器打开公网地址 → 输口令 → 浏览器菜单选「添加到主屏幕」，即成为全屏 App（PWA，已配 manifest 与图标）。
- 后续写**安卓端**时直接复用同一套 API 口径，**不需要另建后端**：
  - `GET /api/status`（带 `X-KB-Token` 头）
  - `POST /api/ask`，body：`{"question":"...","kb":"ai-software-testing","top_k":6}`
  - 未带口令 401；超频 429；排队超时 503；响应里的 `degraded: true` 表示"已配模型但本次降级"。

### 部署到云服务器（Docker / 宝塔）

隧道方案适用于「跑在自己电脑上」。如果以后要搬到云服务器，本项目已经具备容器化能力：

```powershell
# 通用 Docker 部署（云服务器上）
$env:KB_ACCESS_TOKEN="<你的口令>"        # 必填，否则等于裸奔
docker compose up --build -d             # 默认 http://<服务器IP>:18765
```

要点：

1. **云服务器有公网 IP，就不需要隧道了**——直接 `Nginx/Caddy 反代 + 域名 + HTTPS`。
   - **国内服务器绑域名必须 ICP 备案**（约 1–3 周）；不想备案就用境外/香港节点（但境内访问质量会打折）。
   - Caddy 最省事：`your.domain { reverse_proxy 127.0.0.1:18765 }`，自动申请证书。
2. **模型服务怎么接**（`KB_*_BASE` 决定）：
   - 继续用本机 Ollama → 服务器上不可行（除非本机暴露给服务器，不推荐）；
   - 换成 OpenAI 兼容云 API（阿里云百炼 DashScope / 硅基流动等）→ 填 `KB_EMBED_BASE`、`KB_LLM_BASE`、`KB_API_KEY`、`KB_*_MODEL`，服务器配置要求低（2C2G 够）；
   - 自建 GPU 服务器跑 Ollama → 数据与模型完全自控，成本最高。
3. **反代下的真实客户端 IP**：`KB_TRUST_PROXY=1`（默认）会读 `X-Forwarded-For` / `CF-Connecting-IP`；Nginx 记得加 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`，否则限流会把所有请求算到一个 IP 上。
4. **数据持久化**：`docker-compose.yml` 里向量库在具名卷 `kb-data`，知识内容用 `./kb:/kb-in:ro` 挂载。注意卷里只有向量/元数据，**知识 Markdown 仍以仓库为唯一事实来源**。
5. **宝塔面板**：
   - 首选它的 **Docker 模块**——把仓库拉到服务器，用「Compose 模板」指向本项目的 `docker-compose.yml`，在面板里配环境变量（尤其 `KB_ACCESS_TOKEN`）即可；
   - 或者用 **Python 项目管理器**跑 `web/server.py`，再用 **网站 → 反向代理** 指向 `127.0.0.1:18765`，SSL 用面板一键 Let's Encrypt；
   - 无论哪种方式，**上线前务必确认无口令访问 `/api/status` 返回 401**（这是本项目唯一的硬性安全检查）。

### 踩坑记录（本次新增）

4. **并发会让 9B 模型 ROCm OOM 并静默降级**。本机是 AMD RX 7800 XT(16GB)：两个请求同时生成时会报
   `ROCm error: out of memory`，localbrain 随即降级为"纯语义检索"，用户拿到的是片段列表而非 AI 回答，
   而接口看起来一切正常。已加**生成并发闸门**（`KB_MAX_CONCURRENT` 默认 2，超出排队，超时 503），
   并在响应里新增 `degraded` 标志，前端会明确提示"大模型本次未返回结果（显存不足或服务忙）"，
   而不是谎称"未配置模型"。要更彻底：给 Ollama 设 `OLLAMA_NUM_PARALLEL=1`、`OLLAMA_MAX_LOADED_MODELS=2` 后重启 Ollama。
5. **quick tunnel 地址每次重启都会变**（`*.trycloudflare.com` 是随机的）。手机端长期使用建议升级为**命名隧道**：
   `cloudflared tunnel login` → `cloudflared tunnel create kb` → 在 Cloudflare 给域名加 CNAME 指向
   `<tunnel-id>.cfargotunnel.com` → 之后用 `web\tunnel.ps1 -Action start -TunnelName kb` 拿到**固定域名**。
   本方案的鉴权与前端都无需改动。
6. **`.ps1` 里不要写中文输出字符串**。Windows PowerShell 5.1 在脚本无 BOM 时按 GBK 读取，中文字符串会变乱码
   并触发语法错误。`run.ps1` / `tunnel.ps1` 因此保持「注释可中文、**代码字符串全 ASCII**」。
7. **不要用管道调用 `run.ps1` / `tunnel.ps1`**。它们 `Start-Process` 起的常驻进程会继承标准输出句柄，
   管道永不关闭，调用方会一直等下去（表现为"命令卡住直到超时"）。自动化请用
   `Start-Process ... -RedirectStandardOutput <文件>`。
8. **`OLLAMA_HOST=0.0.0.0`**：本机 Ollama 监听所有网卡（且 `OLLAMA_ORIGINS=*`），同一局域网内可直接调用模型。
   隧道只转发 18765，**不会**把 Ollama 暴露到公网；但若不需要局域网访问，建议改回 `127.0.0.1` 再重启 Ollama。
9. **Tailscale Funnel 首次必须由账号主人手动授权一次**：直接跑 `tailscale funnel` 只会打印
   `Funnel is not enabled on your tailnet. To enable, visit: https://login.tailscale.com/f/funnel?node=...`
   然后**挂住等待**（`--yes` 参数替代不了这个授权）。在浏览器点开该链接确认后，再跑一次即可。
10. **计划任务「无限重复」的写法**：`New-ScheduledTaskTrigger -RepetitionDuration ([TimeSpan]::MaxValue)`
    会序列化成 `P99999999DT23H59M59S`，被任务计划拒绝（`The task XML contains a value which is incorrectly
    formatted or out of range`）。正确做法是**只给 `-RepetitionInterval`、不给 `-RepetitionDuration`**——
    Duration 为空即表示无限重复。
11. **快速隧道扛不住重启**：`*.trycloudflare.com` 是随机地址，电脑一重启隧道进程就没了、地址也永久失效
    （这就是「网址打不开了」的直接原因）。**Tailscale Funnel 给的是固定域名**，重启后由计划任务自动重拉，
    这才是「常态化」的关键差别。
12. **`Get-Content` 在 PowerShell 5.1 下默认按 GBK 读文件**：读 UTF-8 中文文件（如生成的日志）会乱码。
    排查时用 `Get-Content -Encoding UTF8`，或用支持 UTF-8 的编辑器打开。
13. **`FileCollector()` 不读配置里的 data_dir**（localbrain 的坑，最隐蔽的一个）。
    `kb/commands/collect.py` 是 `collector = FileCollector()` **无参构造**，而它的 `output_dir`
    默认硬编码为 `~/.knowledge-base/1_collect`。但 sqlite 与 Chroma 走的是 `Config(CONFIG_FILE)`，
    **会正确指向目标库** —— 结果是「DB/向量进了毛选库，文件却落进了测试库」，
    表现出来就是前端条目数对不上。解法：用 `web/kb_ingest.py`（**显式传 `output_dir`**），
    或在 `kb/commands/utils.py` 里给 `CONFIG_FILE` 打补丁后自己构造 collector。
14. **localbrain 的采集 id 是秒级的**：`file_YYYYmmdd_HHMMSS`。同一秒内采集多个文件会**撞 id**，
    而 chunk id 是 `{item_id}_chunk_{i}` —— 于是后写的 chunk **直接覆盖**先写的。
    实测 18 篇在 5 秒内采完，只有 8 篇真正进了向量库，**而且全程没有任何报错**。
    解法：`web/kb_ingest.py` 会在撞 id 时删掉刚写的文件、等 1.1 秒重采，保证 id 唯一。
15. **`_index_content_for_search` 会静默失败**：它内部 `try/except` 后 `return False`
    （chunker 失败时甚至**直接 return 不打印任何日志**）。所以入库脚本**必须检查它的返回值**，
    否则会出现「脚本 18/18 全部 OK，但向量库里只有一半」这种假成功。
16. **索引失败常见诱因是 GPU 争抢**：同时跑批量总结（占满显存）时做入库，embedding 会失败。
    批量生成内容与批量入库**不要并发**。
17. **`python:3.12-slim` 里没有 git**：原 Dockerfile 直接 `pip install "localbrain @ git+https://..."`，
    缺 git 会**构建失败**。已在 Dockerfile 里补 `apt-get install git`，并加了
    `DEBIAN_MIRROR` / `PIP_INDEX` / `GITHUB_PROXY` 三个构建参数供国内网络覆盖。
18. **容器里的配置不能只写 embedding/llm/data_dir**（最隐蔽的一个坑）。
    `storage.persist_directory` 决定 Chroma 目录；少写这一段，检索会落到**默认库**的向量目录，
    表现是「问毛选却返回软件测试的内容」或「直接说找不到文档」。
    现在的做法：把**宿主机的完整配置**挂成 `/config-templates` 模板，`bootstrap_config.py`
    以模板为底，只覆盖 `data_dir` / `storage.persist_directory` / `embedding` / `llm`，其余段原样保留。
19. **诊断时 `docker exec` 必须加 `-i` 才能读 heredoc**：`docker exec ct python - <<'PY'` 会静默无输出，
    看着像"脚本没跑"，其实只是 stdin 没接上。稳妥做法是把脚本 `docker cp` 进去再 `docker exec python /tmp/x.py`。
20. **PowerShell 变量名大小写不敏感**：`deploy.ps1` 里原有的 `$target`（服务 URL）与新加的
    `-Target` 参数是**同一个变量**，赋值 URL 时触发 `ValidateSet` 校验失败。已把内部变量改名为 `$svcUrl`。
21. **VM 的网络是"半个互联网"**：实测 `archive.ubuntu.com`、`download.docker.com`、清华/阿里镜像、
    `docker.m.daocloud.io` 都通；但 **`pypi.org` 与 `registry-1.docker.io` 超时、`github.com` 直连超时**。
    所以 Docker 要配 `registry-mirrors`，pip 要配清华源，GitHub 要走 `gh-proxy.com` 代理。
22. **`netsh interface portproxy` 需要管理员权限**：所以 `-Target vm` 的计划任务用
    `-RunLevel Highest` 注册（计划任务以最高权限运行不需要 UAC 弹窗）。
    副作用：经 portproxy 的请求源 IP 都变成宿主机的，**按 IP 限流会把所有人算作一个 IP**；
    不过公网路径上 Tailscale 会带 `X-Forwarded-For`，所以外网访问的真实 IP 仍然是准的。

---

## 部署到虚拟机（长期服务器形态）

知识库可以整体搬到 VMware 虚拟机里跑（Docker），宿主机只保留「开穿透 + 提供模型」两个职责。
**公网地址与口令均不变。** 完整说明见 [`deploy-vm/README.md`](deploy-vm/README.md)。

```powershell
python web\vm_deploy.py --stage all                          # 一键部署到 VM
powershell -File web\deploy.ps1 -Action ensure -Target vm    # 一键恢复整条链
powershell -File web\vm.ps1      -Action status              # VM 与自启任务状态
```
