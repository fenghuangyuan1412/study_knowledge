# -*- coding: utf-8 -*-
"""
VM（Ubuntu）SSH 操作工具 —— 用于把知识库部署到虚拟机。

用法：
    python web/vm_ssh.py exec "命令"        # 执行命令（sudo 自动带密码）
    python web/vm_ssh.py sudo "命令"        # 以 sudo 执行
    python web/vm_ssh.py put 本地 远端      # 上传文件
    python web/vm_ssh.py putdir 本地目录 远端目录
    python web/vm_ssh.py info               # 环境体检
"""
from __future__ import annotations

import os
import posixpath
import stat
import sys
from pathlib import Path

import paramiko

HOST = os.environ.get("VM_HOST", "192.168.163.128")
USER = os.environ.get("VM_USER", "awei")
PORT = int(os.environ.get("VM_PORT", "22"))

# 密码只从环境变量或 web/.runtime/（已 gitignore）取，绝不写默认值——
# 本仓库是公开仓库，任何字面量凭据都会随 git 历史永久外泄。
PASS_FILE = Path(__file__).resolve().parent / ".runtime" / "vm.pass"


def _resolve_pass() -> str:
    p = (os.environ.get("VM_PASS") or "").strip()
    if p:
        return p
    if PASS_FILE.exists():
        return PASS_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit(
        f"缺少 VM 密码：设环境变量 VM_PASS，或把密码写入 {PASS_FILE}"
        "（该目录已被 .gitignore 排除，不会入库）"
    )


PASS = _resolve_pass()


def connect() -> paramiko.SSHClient:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, port=PORT, username=USER, password=PASS,
                look_for_keys=False, allow_agent=False,
                timeout=15, banner_timeout=20, auth_timeout=20)
    return cli


def run(cli: paramiko.SSHClient, cmd: str, sudo: bool = False, timeout: int = 900,
        quiet: bool = False) -> tuple[int, str]:
    if sudo:
        # -S 从 stdin 读密码；-p '' 不打印提示
        cmd = f"sudo -S -p '' bash -lc {shell_quote(cmd)}"
    else:
        cmd = f"bash -lc {shell_quote(cmd)}"
    _in, out, err = cli.exec_command(cmd, timeout=timeout, get_pty=False)
    if sudo:
        _in.write(PASS + "\n")
        _in.flush()
    o = out.read().decode(errors="ignore")
    e = err.read().decode(errors="ignore")
    rc = out.channel.recv_exit_status()
    if not quiet:
        if o.strip():
            print(o.rstrip())
        if e.strip():
            print("[stderr]", e.rstrip(), file=sys.stderr)
    return rc, o


def shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


# 上传目录时排除的路径片段
EXCLUDES = {".runtime", "__pycache__", ".git", "node_modules", ".venv", ".pytest_cache"}


def put_dir(cli: paramiko.SSHClient, local: Path, remote: str) -> int:
    sftp = cli.open_sftp()

    def ensure(d: str):
        parts, cur = d.strip("/").split("/"), ""
        for p in parts:
            cur += "/" + p
            try:
                sftp.stat(cur)
            except IOError:
                sftp.mkdir(cur)

    n = 0
    for f in sorted(local.rglob("*")):
        rel_parts = f.relative_to(local).parts
        if any(p in EXCLUDES for p in rel_parts):
            continue
        rel = f.relative_to(local).as_posix()
        target = posixpath.join(remote, rel)
        if f.is_dir():
            ensure(target)
            continue
        ensure(posixpath.dirname(target))
        sftp.put(str(f), target)
        n += 1
    sftp.close()
    return n


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    action = sys.argv[1]
    cli = connect()
    try:
        if action == "exec":
            rc, _ = run(cli, sys.argv[2])
            return rc
        if action == "sudo":
            rc, _ = run(cli, sys.argv[2], sudo=True)
            return rc
        if action == "put":
            sftp = cli.open_sftp()
            sftp.put(sys.argv[2], sys.argv[3])
            sftp.close()
            print(f"uploaded -> {sys.argv[3]}")
            return 0
        if action == "putdir":
            n = put_dir(cli, Path(sys.argv[2]), sys.argv[3])
            print(f"uploaded {n} files -> {sys.argv[3]}")
            return 0
        if action == "info":
            cmds = [
                "echo '--- os ---'; cat /etc/os-release | head -2",
                "echo '--- kernel ---'; uname -r",
                "echo '--- cpu/mem ---'; nproc; free -h | head -2",
                "echo '--- disk ---'; df -h / | tail -1",
                "echo '--- ip ---'; hostname -I",
                "echo '--- sudo ---'; sudo -n true 2>/dev/null && echo NOPASSWD || echo NEEDS_PASSWORD",
                "echo '--- docker ---'; which docker || echo no-docker",
                "echo '--- docker compose ---'; docker compose version 2>/dev/null || echo no-compose-plugin",
                "echo '--- python ---'; python3 --version 2>/dev/null || echo no-python3",
                "echo '--- net ---'; curl -s -o /dev/null -w 'pypi=%{http_code} ' --max-time 8 https://pypi.org/simple/ ; curl -s -o /dev/null -w 'github=%{http_code} ' --max-time 8 https://github.com ; curl -s -o /dev/null -w 'aliyun-mirror=%{http_code}' --max-time 8 https://mirrors.aliyun.com ; echo",
                "echo '--- host model svc reachable? ---'; curl -s -o /dev/null -w 'host8000=%{http_code}\n' --max-time 8 http://192.168.163.1:8000/ || echo host8000=unreachable",
            ]
            for c in cmds:
                run(cli, c, quiet=False)
            return 0
        print(__doc__)
        return 1
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())
