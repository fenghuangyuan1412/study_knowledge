#!/usr/bin/env bash
# 容器入口：生成配置 -> 初始化知识库(首次) -> 可选导入知识 -> 启动 Web 问答服务
set -e

echo "[kb] bootstrap localbrain config from env..."
python /app/web/docker/bootstrap_config.py

if [ ! -f "$HOME/.knowledge-base/db/metadata.db" ]; then
  echo "[kb] initializing knowledge base (first run)..."
  localbrain init setup --no-sample
fi

if [ -n "${KB_IMPORT_DIR:-}" ] && [ -d "$KB_IMPORT_DIR" ] \
   && find "$KB_IMPORT_DIR" -maxdepth 2 -name '*.md' -print -quit 2>/dev/null | grep -q .; then
  echo "[kb] importing knowledge from $KB_IMPORT_DIR"
  python /app/web/docker/kb_import.py "$KB_IMPORT_DIR"
fi

echo "[kb] starting web server on ${HOST:-0.0.0.0}:${PORT:-18765}"
exec "$@"
