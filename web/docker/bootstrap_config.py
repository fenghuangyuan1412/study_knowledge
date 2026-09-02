# -*- coding: utf-8 -*-
"""容器启动时用环境变量生成/覆盖 ~/.localbrain/config.yaml 的 embedding/llm 两段。

环境变量（见 docker-compose.yml）：
  KB_EMBED_MODEL / KB_EMBED_BASE / KB_LLM_MODEL / KB_LLM_BASE / KB_API_KEY / KB_THINK
保留配置文件中其它段（chunking/storage/query...），只覆盖模型接线。
"""
import os
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".localbrain"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def main() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if CONFIG_FILE.exists():
        cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}

    api_key = os.environ.get("KB_API_KEY", "not-needed").strip() or "not-needed"

    cfg["embedding"] = {
        "provider": "litellm",
        "model": os.environ.get("KB_EMBED_MODEL", "ollama/bge-m3"),
        "api_key": api_key,
        "base_url": os.environ.get("KB_EMBED_BASE", "http://host.docker.internal:11434"),
    }
    llm = {
        "provider": "litellm",
        "model": os.environ.get("KB_LLM_MODEL", "ollama/qwen3.5:9b"),
        "api_key": api_key,
        "base_url": os.environ.get("KB_LLM_BASE", "http://host.docker.internal:11434"),
    }
    if os.environ.get("KB_THINK") is not None:
        llm["think"] = _truthy(os.environ.get("KB_THINK", "false"))
    cfg["llm"] = llm

    CONFIG_FILE.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"[kb] config written: {CONFIG_FILE} (embed={cfg['embedding']['model']}, llm={llm['model']})")


if __name__ == "__main__":
    main()
