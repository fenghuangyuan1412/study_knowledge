# -*- coding: utf-8 -*-
"""容器启动时生成 localbrain 配置：**以宿主机的完整配置为模板**，只覆盖必要字段。

为什么不能只写 embedding/llm：localbrain 的检索路径还依赖
`storage.persist_directory`（Chroma 目录）、`chunking`、`query` 等段。
之前只写三段，缺 `storage.persist_directory` → 毛选库的 RAG 会去读默认库的向量目录，
表现为「问毛选却返回软件测试的内容 / 直接说找不到文档」。

做法：
  1. 从 /config-templates/<文件名> 读模板（由 compose 挂载宿主机的真实配置，只读）；
  2. 覆盖 data_dir、storage.persist_directory、embedding、llm；
  3. 其余段（chunking/query/logging/...）原样保留，保证容器与宿主机行为一致。

环境变量：
  KB_EMBED_MODEL / KB_EMBED_BASE / KB_LLM_MODEL / KB_LLM_BASE / KB_API_KEY / KB_THINK
  KB_DATA_DIR / KB_MAOXUAN_DATA_DIR  可选，数据目录
"""
import os
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".localbrain"
TEMPLATE_DIR = Path("/config-templates")

TARGETS = [
    ("config.yaml", "~/.knowledge-base", "KB_DATA_DIR"),
    ("config-maoxuan.yaml", "~/.knowledge-base-maoxuan", "KB_MAOXUAN_DATA_DIR"),
]


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _load_base(dest: Path) -> dict:
    """优先用模板（与宿主机一致），其次用已存在的目标文件。"""
    for cand in (TEMPLATE_DIR / dest.name, dest):
        if cand.exists():
            try:
                data = yaml.safe_load(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as e:  # noqa: BLE001
                print(f"[kb] WARN: cannot parse {cand}: {e}")
    return {}


def main() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get("KB_API_KEY", "not-needed").strip() or "not-needed"

    for name, default_data_dir, env_key in TARGETS:
        dest = CONFIG_DIR / name
        cfg = _load_base(dest)

        data_dir = os.environ.get(env_key, default_data_dir)
        cfg["data_dir"] = data_dir
        # 关键：显式指定向量库目录，否则会落到默认库（跨库串味）
        cfg.setdefault("storage", {})
        cfg["storage"]["type"] = cfg["storage"].get("type", "chroma")
        cfg["storage"]["persist_directory"] = f"{data_dir}/db/chroma"

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

        dest.write_text(
            yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        print(f"[kb] config written: {dest} (data_dir={data_dir}, "
              f"chroma={cfg['storage']['persist_directory']}, "
              f"template={'yes' if (TEMPLATE_DIR / name).exists() else 'no'}, "
              f"sections={len(cfg)})")


if __name__ == "__main__":
    main()
