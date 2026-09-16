# 虚拟机（Ubuntu）长期部署

把知识库从「跑在自己电脑上」升级为「跑在 VMware 虚拟机里」，作为长期服务器使用。

## 架构

```
公网用户
   │  https://pc-202412121713.tail69ff66.ts.net  ← 永久地址，始终不变
   ▼
Windows 宿主机
   ├─ Tailscale Funnel   → 127.0.0.1:18765
   ├─ netsh portproxy    0.0.0.0:18765 → 192.168.163.128:18765
   ├─ Ollama  :11434     （模型服务，VM 直连 192.168.163.1:11434）
   └─ New API :8000      （WSL2，portproxy → 172.27.16.245:3000）
          ▲
          │ VMware NAT（宿主 = 192.168.163.1）
   ┌──────┴───────────────────────────────────────────┐
   │ VM  Ubuntu 24.04  192.168.163.128                │
   │  ├─ kb-web   容器 :18765  FastAPI + localbrain   │
   │  │    ├─ 知识库 A  data/knowledge-base           │
   │  │    └─ 知识库 B  data/knowledge-base-maoxuan   │
   │  └─ npm      容器 :80/:443/:81  Nginx Proxy Mgr  │ ← 后门：以后加站点
   └──────────────────────────────────────────────────┘
```

**为什么公网地址不变**：Tailscale 跑在宿主机上，Funnel 只能转发宿主机的本地端口。
所以让宿主机把 18765 用 `netsh portproxy` 转给 VM —— 对 Tailscale 而言后端没变，
**朋友手里的链接和口令都不需要改**。

## 一键部署

在 Windows 上（需要 VM 已开机、SSH 可登录）：

```powershell
python web\vm_deploy.py --stage check     # 体检：SSH/Docker/磁盘/模型服务
python web\vm_deploy.py --stage upload    # 上传应用 + 两个库的数据
python web\vm_deploy.py --stage env       # 生成 .env（含访问口令）
python web\vm_deploy.py --stage build     # 构建镜像
python web\vm_deploy.py --stage up        # 启动
python web\vm_deploy.py --stage verify    # 端到端验证
python web\vm_deploy.py --stage all       # 或一步到位
```

改完 `web/` 下的代码后，只需 `--stage upload` + `--stage build` + `--stage up`。

## 日常运维

```bash
# 在 VM 上
cd /opt/study-knowledge
docker compose ps
docker compose logs -f kb-web
docker compose restart kb-web
docker compose pull && docker compose up -d      # 更新 NPM 等镜像
```

在 Windows 上：

```powershell
powershell -File web\vm.ps1      -Action status      # VM 状态 + 自启任务
powershell -File web\vm.ps1      -Action start|stop
powershell -File web\deploy.ps1  -Action status      # 服务链状态
powershell -File web\deploy.ps1  -Action ensure -Target vm   # 一键恢复整条链
```

## 模型服务怎么接

`.env` 里两个变量决定（改完 `docker compose up -d` 生效）：

| 方案 | 配置 | 说明 |
| --- | --- | --- |
| **宿主机 Ollama（当前默认）** | `KB_EMBED_BASE` / `KB_LLM_BASE` = `http://host.docker.internal:11434`，`KB_API_KEY=not-needed` | 不需要 key，开箱即用；模型 `bge-m3` + `qwen3.5:9b` |
| **宿主机 New API** | 改成 `http://host.docker.internal:8000/v1`，并把 `KB_API_KEY` 填成 New API 的令牌 | 走 New API 可统一计费/换模型；`/v1/models` 无 token 返回 401 |

`host.docker.internal` 在 compose 里固定映射到 `192.168.163.1`（VMware NAT 下的宿主机地址），
所以容器里不用写死 IP。

> 你说的 `localhost:8000/channels` 是宿主机上的 New API 管理界面。注意**在 VM 里 `localhost` 是 VM 自己**，
> 访问宿主机的服务要用 `192.168.163.1`（compose 里已别名成 `host.docker.internal`）。

## 后门：以后往上加东西

已经留好的位置：

| 用途 | 怎么用 |
| --- | --- |
| **加新网站** | 新服务加进 `docker-compose.yml`，然后到 `http://192.168.163.128:81`（NPM）里加 Proxy Host：域名 → `容器名:端口`，证书一键申请 |
| **80 / 443 端口** | 被 NPM 占用，留给所有网站统一入口；不用改一条条 iptables |
| **new-api 穿透上服务器** | 要么把 New API 直接搬到这台 VM（`docker run` + NPM 反代），要么在宿主机加一条 portproxy 把端口引过来，和现在 18765 的做法一样 |
| **再开端口** | VM 上 `docker compose` 里加 `ports:`，宿主机若要公网可达再加一条 `netsh interface portproxy add v4tov4 listenport=<P> listenaddress=0.0.0.0 connectport=<P> connectaddress=192.168.163.128` |
| **数据持久化** | `./data/*` 与 `./npm/*` 都是宿主目录挂载，容器重建不丢数据 |

NPM 首次登录：`http://192.168.163.128:81` → `admin@example.com` / `changeme`（**登录后立刻改**）。

## 开机自启链

| 任务 | 触发 | 作用 |
| --- | --- | --- |
| `StudyKnowledge-VM-AutoStart` | 登录时 | `vmrun start "<vmx>" nogui` 启动虚拟机 |
| `StudyKnowledge-KB-AutoDeploy` | 登录时 | `deploy.ps1 -Action ensure -Target vm`：停宿主服务 → 等 VM → 端口转发 → 开 Funnel → 校验口令守卫 |

两个任务都是**隐藏窗口、不重复触发**（之前每 5 分钟弹一次窗口的问题已修掉）。
VM 内 Docker 服务本身是 `systemctl enable`，容器是 `restart: unless-stopped`，所以 VM 一启动容器就起来。

> 需要**开机（未登录）就可用**的话，把两个任务的触发改成 `-AtStartup` 并以 SYSTEM 运行；
> 但 `tailscale funnel` 与 `vmrun` 在用户会话外行为不稳定，当前按"登录后自动恢复"设计。

## 排错

| 现象 | 检查 |
| --- | --- |
| 公网 502 | 宿主机 `deploy.ps1 -Action status`；VM 里 `docker compose ps` |
| 页面能开、提问报 401 | 口令不一致：对一下 `.env` 里的 `KB_ACCESS_TOKEN` |
| 提问返回片段而非 AI 回答 | 模型服务不通：VM 里 `docker exec kb-web python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags',timeout=8).status)"` |
| **问 A 库却返回 B 库内容** | `bootstrap_config.py` 必须带上 `storage.persist_directory`；本项目的做法是把宿主机完整配置挂成 `/config-templates` 模板 |
| 磁盘告急 | `docker system prune -af`，或给 VM 扩盘；20G 盘装完约用 12G |
