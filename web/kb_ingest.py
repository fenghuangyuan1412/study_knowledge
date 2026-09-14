# -*- coding: utf-8 -*-
"""
按知识库入库 Markdown（localbrain collect）。

为什么要这个脚本：localbrain CLI 的 CONFIG_FILE 是**硬编码**在
`kb/commands/utils.py` 的（`~/.localbrain/config.yaml`），没有命令行参数或环境变量
可以切换。本项目有两个独立数据实例（AI 软件测试 / 毛选），所以这里在调用前把
各模块里的 CONFIG_FILE 全部改写成目标库的配置路径。

注意：**收集阶段就会写 Chroma 向量**（`_index_content_for_search`），
`localbrain mine` 只补 sqlite（实体/关系/主题），因此本脚本只做 collect 即可满足问答检索。

用法：
    python web/kb_ingest.py --kb maoxuan --glob "kb/maoxuan/batch-002/items/*.md"
    python web/kb_ingest.py --kb ai-software-testing --glob "kb/ai-software-testing/batch-002/items/*.md"
    python web/kb_ingest.py --kb maoxuan --glob "..." --dry-run
"""
from __future__ import annotations

import argparse
import glob as globmod
import re
import sys
from pathlib import Path

PROFILES = {
    "ai-software-testing": {
        "label": "AI 软件测试",
        "config": Path.home() / ".localbrain" / "config.yaml",
    },
    "maoxuan": {
        "label": "毛选",
        "config": Path.home() / ".localbrain" / "config-maoxuan.yaml",
    },
}


def patch_config(config_path: Path) -> None:
    """把 kb 各模块里的 CONFIG_FILE 指向目标配置。

    collect.py 用的是 `from kb.commands.utils import CONFIG_FILE`，那是**值拷贝**，
    所以必须逐模块改写，只改 utils 不生效。
    """
    import kb.commands.utils as U  # noqa: F401  确保已导入

    patched = []
    for name, mod in list(sys.modules.items()):
        if not name.startswith("kb"):
            continue
        if hasattr(mod, "CONFIG_FILE"):
            setattr(mod, "CONFIG_FILE", config_path)
            patched.append(name)
    return None


def read_frontmatter(path: Path) -> tuple[str, list[str]]:
    """从 md 里取 title 与 tags（tags 形如 `[a, b, c]`）。"""
    text = path.read_text(encoding="utf-8", errors="ignore")[:1500]
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    block = m.group(1) if m else ""
    title = ""
    mt = re.search(r"^title:\s*(.*)$", block, re.M)
    if mt:
        title = mt.group(1).strip().strip('"').strip("'")
    tags: list[str] = []
    mg = re.search(r"^tags:\s*\[(.*?)\]\s*$", block, re.M)
    if mg:
        tags = [t.strip().strip('"').strip("'") for t in mg.group(1).split(",") if t.strip()]
    return (title or path.stem), tags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True, choices=sorted(PROFILES))
    ap.add_argument("--glob", required=True, help='相对仓库根的文件通配，如 "kb/maoxuan/batch-002/items/*.md"')
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    prof = PROFILES[args.kb]
    cfg = prof["config"]
    print(f"[kb] {args.kb} ({prof['label']})")
    print(f"[kb] config : {cfg}")
    if not cfg.exists():
        print(f"[kb] ERROR: config not found: {cfg}")
        return 1

    data_dir = None
    try:
        import yaml  # type: ignore
        data_dir = (yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}).get("data_dir")
    except Exception:  # noqa: BLE001
        pass
    print(f"[kb] data   : {data_dir}")

    patch_config(cfg)

    files = sorted(Path(p) for p in globmod.glob(str(Path(args.repo) / args.glob)))
    if not files:
        print(f"[kb] no files matched: {args.glob}")
        return 1
    print(f"[kb] files  : {len(files)}\n")

    if args.dry_run:
        for f in files:
            title, tags = read_frontmatter(f)
            print(f"  DRY {f.name}  title={title!r}  tags={tags}")
        return 0

    from click.testing import CliRunner

    from kb.cli import cli

    runner = CliRunner()
    ok = fail = 0
    for i, f in enumerate(files, 1):
        title, tags = read_frontmatter(f)
        argv = ["collect", "file", "add", str(f), "--title", title, "--no-auto-extract"]
        for t in tags:
            argv += ["-t", t]
        res = runner.invoke(cli, argv, catch_exceptions=False)
        out = (res.output or "").strip()
        good = res.exit_code == 0
        ok += good
        fail += (not good)
        mark = "OK " if good else "ERR"
        print(f"  [{i}/{len(files)}] {mark} {f.name}  ({title})")
        if not good:
            print("       " + out.replace("\n", "\n       ")[:400])

    print(f"\n[kb] done: ok={ok} fail={fail}")
    print("[kb] 提示：本阶段已写 Chroma 向量；如需实体/关系，再跑 `localbrain mine run`")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
