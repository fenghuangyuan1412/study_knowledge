# -*- coding: utf-8 -*-
"""
把知识库一键部署到 Ubuntu 虚拟机（Docker）。

做四件事：把应用与**现有向量数据**传到 VM → 生成 .env → 构建镜像 → 起编排 → 端到端验证。
传数据而不是重新入库，是为了让 VM 上的回答与宿主机完全一致（两个库都带过去）。

用法：
    python web/vm_deploy.py --stage check        # 体检：SSH/Docker/网络/模型服务
    python web/vm_deploy.py --stage upload       # 上传应用 + 两个库的数据
    python web/vm_deploy.py --stage env          # 生成 .env（含访问口令）
    python web/vm_deploy.py --stage build        # 构建镜像（约数分钟）
    python web/vm_deploy.py --stage up           # 启动编排
    python web/vm_deploy.py --stage verify       # 端到端验证
    python web/vm_deploy.py --stage all          # 全流程

依赖：web/vm_ssh.py（同目录）
"""
from __future__ import annotations

import argparse
import os
import posixpath
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import vm_ssh  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
REMOTE = "/opt/study-knowledge"
HOST_GATEWAY = os.environ.get("VM_HOST_GATEWAY", "192.168.163.1")
TOKEN = os.environ.get("KB_ACCESS_TOKEN") or ""

DATA_DIRS = {
    Path.home() / ".knowledge-base": "data/knowledge-base",
    Path.home() / ".knowledge-base-maoxuan": "data/knowledge-base-maoxuan",
}


def log(msg: str) -> None:
    print(f"\n\033[1;36m>>> {msg}\033[0m" if os.name != "nt" else f"\n>>> {msg}", flush=True)


# --------------------------------------------------------------------------- #
def stage_check(cli) -> bool:
    log("体检：SSH / Docker / 磁盘 / 模型服务")
    cmds = [
        ("os", "cat /etc/os-release | head -2 | tr '\\n' ' '; echo"),
        ("cpu/mem", "echo cores=$(nproc) mem=$(free -m | awk '/Mem:/{print $2}')MB"),
        ("disk", "df -h / | tail -1"),
        ("docker", "docker --version && docker compose version"),
        ("ssh user", "whoami; hostname -I"),
        ("host ollama", "python3 -c \"import urllib.request,json;"
                        "d=json.load(urllib.request.urlopen('http://" + HOST_GATEWAY +
                        ":11434/api/tags',timeout=8));print('models',len(d['models']))\""
                        " 2>&1 | tail -1"),
        ("host newapi", "python3 -c \"import urllib.request;"
                        "print('http',urllib.request.urlopen('http://" + HOST_GATEWAY +
                        ":8000/api/status',timeout=8).status)\" 2>&1 | tail -1"),
    ]
    ok = True
    for name, c in cmds:
        rc, out = vm_ssh.run(cli, c, quiet=True)
        line = (out or "").strip().replace("\n", " | ")
        print(f"  [{name}] {line}")
        if rc != 0:
            ok = False
    return ok


# --------------------------------------------------------------------------- #
def stage_upload(cli) -> bool:
    log("上传应用")
    # /opt 属于 root，先用 sudo 建目录并把归属改给登录用户，后续 SFTP 才能写入
    vm_ssh.run(cli,
               f"mkdir -p {REMOTE} && chown -R {vm_ssh.USER}:{vm_ssh.USER} {REMOTE}",
               sudo=True, quiet=True)
    vm_ssh.run(cli, f"mkdir -p {REMOTE}/data {REMOTE}/npm", quiet=True)

    sftp = cli.open_sftp()
    sftp.put(str(REPO / "Dockerfile"), f"{REMOTE}/Dockerfile")
    sftp.put(str(REPO / "web" / "deploy-vm" / "docker-compose.vm.yml"),
             f"{REMOTE}/docker-compose.yml")
    sftp.close()
    print("  Dockerfile + docker-compose.yml")

    n = vm_ssh.put_dir(cli, REPO / "web", f"{REMOTE}/web")
    print(f"  web/  ({n} files)")
    n = vm_ssh.put_dir(cli, REPO / "kb", f"{REMOTE}/kb")
    print(f"  kb/   ({n} files)")

    log("上传两个知识库的数据（向量库 + 元数据 + 已采集原文）")
    for local, rel in DATA_DIRS.items():
        if not local.exists():
            print(f"  !! 本地不存在，跳过：{local}")
            continue
        n = vm_ssh.put_dir(cli, local, f"{REMOTE}/{rel}")
        print(f"  {local.name} -> {rel}  ({n} files)")
    return True


# --------------------------------------------------------------------------- #
def stage_env(cli) -> bool:
    log("生成 .env")
    token = TOKEN
    if not token:
        import secrets
        import string
        alphabet = string.ascii_lowercase + string.digits
        token = "".join(secrets.choice(alphabet) for _ in range(14))
        print(f"  （宿主环境没有 KB_ACCESS_TOKEN，已生成新的：{token}）")
    env = f"""# 知识库 VM 部署环境变量（本文件含口令，不要提交到 git）
KB_ACCESS_TOKEN={token}
KB_PORT=18765
HOST_GATEWAY={HOST_GATEWAY}

# 模型接线：默认走宿主机 Ollama（无需 key）。
# 要用宿主机的 New API 就改成下面两行并填 KB_API_KEY：
#   KB_EMBED_BASE=http://host.docker.internal:8000/v1
#   KB_LLM_BASE=http://host.docker.internal:8000/v1
KB_EMBED_MODEL=ollama/bge-m3
KB_EMBED_BASE=http://host.docker.internal:11434
KB_LLM_MODEL=ollama/qwen3.5:9b
KB_LLM_BASE=http://host.docker.internal:11434
KB_API_KEY=not-needed
KB_THINK=false

# 访问控制
KB_RATE_LIMIT=60
KB_AUTH_FAIL_LIMIT=10
KB_MAX_CONCURRENT=2
KB_QUEUE_TIMEOUT=180

# 构建加速（国内网络必须）
DEBIAN_MIRROR=mirrors.tuna.tsinghua.edu.cn
PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
GITHUB_PROXY=https://gh-proxy.com/
"""
    sftp = cli.open_sftp()
    with sftp.open(f"{REMOTE}/.env", "w") as fh:
        fh.write(env)
    sftp.close()
    vm_ssh.run(cli, f"chmod 600 {REMOTE}/.env", quiet=True)
    print(f"  已写入 {REMOTE}/.env（口令 {token}）")
    return True


# --------------------------------------------------------------------------- #
def stage_build(cli, timeout: int = 3600) -> bool:
    log("构建镜像（pypi 用清华源、GitHub 走 gh-proxy，约数分钟）")
    rc, _ = vm_ssh.run(cli, f"cd {REMOTE} && docker compose build 2>&1 | tail -40",
                       timeout=timeout)
    return rc == 0


def stage_up(cli) -> bool:
    log("启动编排")
    rc, _ = vm_ssh.run(cli, f"cd {REMOTE} && docker compose up -d 2>&1 | tail -20")
    if rc != 0:
        vm_ssh.run(cli, f"cd {REMOTE} && docker compose logs --tail=40 kb-web")
        return False
    return True


def stage_verify(cli) -> bool:
    import time
    log("端到端验证")
    token = TOKEN
    # 从远端 .env 读回口令（可能是新生成的）
    rc, out = vm_ssh.run(cli, f"grep '^KB_ACCESS_TOKEN=' {REMOTE}/.env | cut -d= -f2", quiet=True)
    remote_token = (out or "").strip() or token
    ip = vm_ssh.HOST

    for i in range(30):
        rc, out = vm_ssh.run(
            cli,
            f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://127.0.0.1:18765/api/status || true",
            quiet=True,
        )
        code = (out or "").strip()
        if code in ("200", "401"):
            print(f"  容器已就绪（{i*5}s，http={code}）")
            break
        time.sleep(5)
    else:
        vm_ssh.run(cli, f"cd {REMOTE} && docker compose logs --tail=50 kb-web")
        return False

    checks = [
        ("本机 页面 /", f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:18765/"),
        ("本机 无口令", f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:18765/api/status"),
        ("本机 带口令", f"curl -s -o /dev/null -w '%{{http_code}}' -H 'X-KB-Token: {remote_token}' http://127.0.0.1:18765/api/status"),
        ("局域网 带口令", f"curl -s -o /dev/null -w '%{{http_code}}' -H 'X-KB-Token: {remote_token}' http://{ip}:18765/api/status"),
        ("NPM 面板", f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:81/"),
    ]
    ok = True
    for name, c in checks:
        rc, out = vm_ssh.run(cli, c, quiet=True)
        v = (out or "").strip()
        print(f"  {name}: {v}")
        if v not in ("200", "401", "302"):
            ok = False

    rc, out = vm_ssh.run(
        cli, f"curl -s -H 'X-KB-Token: {remote_token}' http://127.0.0.1:18765/api/status",
        quiet=True)
    print(f"  status: {(out or '').strip()[:400]}")
    print(f"\n  访问地址： http://{ip}:18765/   口令：{remote_token}")
    print(f"  NPM 面板： http://{ip}:81/      (admin@example.com / changeme，登录后请立刻改)")
    return ok


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["check", "upload", "env", "build", "up", "verify", "all"])
    args = ap.parse_args()

    cli = vm_ssh.connect()
    try:
        stages = (["check", "upload", "env", "build", "up", "verify"]
                  if args.stage == "all" else [args.stage])
        for s in stages:
            fn = {"check": stage_check, "upload": stage_upload, "env": stage_env,
                  "build": stage_build, "up": stage_up, "verify": stage_verify}[s]
            if not fn(cli):
                print(f"\n!! 阶段 {s} 失败，中止")
                return 1
        print("\n完成。")
        return 0
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())
