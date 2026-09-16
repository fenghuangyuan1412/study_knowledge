#!/usr/bin/env bash
# 在 Ubuntu 虚拟机上安装 Docker + 配置国内镜像源。
#
# 背景：这台 VM 只能访问 archive.ubuntu.com / download.docker.com / 国内镜像，
#       **pypi.org 与 registry-1.docker.io 均不可达**，所以必须配镜像：
#   - Docker 镜像加速：docker.m.daocloud.io（实测可达）
#   - pip 索引：pypi.tuna.tsinghua.edu.cn（实测可达）
#   - GitHub：github.com 直连超时，用 gh-proxy.com / ghproxy.net 代理（实测可达）
#
# 用法：sudo bash bootstrap-docker.sh
set -euo pipefail

log() { echo -e "\n\033[1;32m>>> $*\033[0m"; }
export DEBIAN_FRONTEND=noninteractive

if command -v docker >/dev/null 2>&1; then
  log "Docker 已安装：$(docker --version)"
else
  log "1/4 安装基础依赖"
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg lsb-release

  log "2/4 添加 Docker 官方源（download.docker.com 实测可达）"
  install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
  fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list

  log "3/4 安装 Docker Engine + Compose 插件"
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io \
                     docker-buildx-plugin docker-compose-plugin
fi

log "4/4 配置镜像加速与日志"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "registry-mirrors": ["https://docker.m.daocloud.io"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
systemctl enable docker
systemctl restart docker
sleep 2

# 让非 root 用户免 sudo 用 docker
if id awei >/dev/null 2>&1; then
  usermod -aG docker awei || true
fi

# pip 镜像（构建镜像时容器内也会用到）
mkdir -p /etc/pip
cat > /etc/pip.conf <<'CONF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 60
CONF

log "完成"
docker --version
docker compose version
docker info 2>/dev/null | grep -A3 "Registry Mirrors" || true
echo
echo "提示：awei 用户需要重新登录（或 newgrp docker）才能免 sudo 使用 docker。"
