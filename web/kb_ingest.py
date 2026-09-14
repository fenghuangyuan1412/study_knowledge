# -*- coding: utf-8 -*-
"""
按知识库入库 Markdown（localbrain collect）。

为什么需要这个脚本 —— 两个 localbrain 的坑：

1. **CLI 的 CONFIG_FILE 是硬编码的**（`kb/commands/utils.py` 里 `~/.localbrain/config.yaml`），
   没有命令行参数也没有环境变量可切。本项目有两个独立数据实例（AI 软件测试 / 毛选），
   所以这里先把所有 kb 模块的 CONFIG_FILE 改写成目标库的配置。
2. **`FileCollector()` 无参构造时 output_dir 硬编码为 `~/.knowledge-base/1_collect`，不读 config**
   （`kb/collectors/file_collector.py`）。也就是说：sqlite/Chroma 会进目标库，**文件却会落到默认库**。
   踩过一次（18 篇毛选总结的文件落进了测试库），所以这里**显式传 output_dir**。

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
import time
from datetime import datetime
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


def patch_config(config_path: Path) -> list[str]:
    """把 kb 各模块里的 CONFIG_FILE 指向目标配置。

    collect.py 用的是 `from kb.commands.utils import CONFIG_FILE`，那是**值拷贝**，
    所以必须逐模块改写；只改 utils 不生效。
    """
    import kb.commands.utils  # noqa: F401  确保已导入

    patched = []
    for name, mod in list(sys.modules.items()):
        if name.startswith("kb") and hasattr(mod, "CONFIG_FILE"):
            setattr(mod, "CONFIG_FILE", config_path)
            patched.append(name)
    return patched


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
    ap.add_argument("--glob", required=True,
                    help='相对仓库根的文件通配，如 "kb/maoxuan/batch-002/items/*.md"')
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    prof = PROFILES[args.kb]
    cfg_path = prof["config"]
    print(f"[kb] {args.kb} ({prof['label']})")
    print(f"[kb] config : {cfg_path}")
    if not cfg_path.exists():
        print(f"[kb] ERROR: config not found: {cfg_path}")
        return 1

    files = sorted(Path(p) for p in globmod.glob(str(Path(args.repo) / args.glob)))
    if not files:
        print(f"[kb] no files matched: {args.glob}")
        return 1

    if args.dry_run:
        print(f"[kb] files  : {len(files)} (dry-run)\n")
        for f in files:
            title, tags = read_frontmatter(f)
            print(f"  DRY {f.name}  title={title!r}  tags={tags}")
        return 0

    patch_config(cfg_path)

    from kb.collectors import FileCollector
    from kb.commands.utils import _get_sqlite_storage, _index_content_for_search

    from kb.config import Config, expand_path

    cfg = Config(cfg_path)
    data_dir = expand_path(str(cfg.get("data_dir", "~/.knowledge-base")))
    collect_dir = Path(data_dir) / "1_collect"
    print(f"[kb] data   : {data_dir}")
    print(f"[kb] files  : {len(files)}\n")

    # 关键：显式指定 output_dir，否则文件会被写到 ~/.knowledge-base
    collector = FileCollector(output_dir=collect_dir)
    storage = _get_sqlite_storage()

    ok = fail = 0
    used_ids: set[str] = set()
    for i, f in enumerate(files, 1):
        title, tags = read_frontmatter(f)
        try:
            # 采集 id 是**秒级**的（file_YYYYmmdd_HHMMSS）。同一秒采集多个文件会撞 id，
            # 而 chunk id 是 {item_id}_chunk_{i} —— 于是后写的直接覆盖先写的。
            # 实测 18 篇里只有 8 篇真正进了向量库，且过程完全静默。
            result = None
            item_id = None
            for attempt in range(6):
                result = collector.collect(source=f, tags=tags or None, title=title,
                                           skip_existing=False, storage=storage)
                if not result.success:
                    raise RuntimeError("collector returned success=False")
                item_id = (result.metadata or {}).get("id")
                if item_id and item_id not in used_ids:
                    break
                # 撞 id：删掉刚写的文件，等一秒让时间戳变化后重采
                try:
                    Path(result.file_path).unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1.1)
            if not item_id or item_id in used_ids:
                raise RuntimeError(f"could not obtain a unique item id (last={item_id})")
            used_ids.add(item_id)

            storage.add_knowledge(
                id=item_id,
                title=result.title or title,
                content_type="file",
                source=str(f),
                collected_at=datetime.now().isoformat(),
                summary="",
                word_count=result.word_count,
                file_path=str(result.file_path),
                content_hash=result.content_hash,
            )
            if tags:
                storage.add_tags(item_id, tags)

            content = Path(result.file_path).read_text(encoding="utf-8", errors="ignore")
            indexed = _index_content_for_search(
                item_id=item_id, content=content, title=result.title or title,
                tags=tags, source=str(f), content_type="file",
            )
            # 这个函数内部 except 后返回 False（且 chunker 失败时静默 return），
            # 不检查返回值就会「看起来成功、其实没进向量库」。
            if not indexed:
                raise RuntimeError("indexing returned False -> vector NOT written")
            ok += 1
            print(f"  [{i}/{len(files)}] OK  {f.name}  id={item_id}  -> {Path(result.file_path).name}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  [{i}/{len(files)}] ERR {f.name}  {type(e).__name__}: {e}")

    print(f"\n[kb] done: ok={ok} fail={fail}")
    print(f"[kb] 已写入 {collect_dir}")
    print("[kb] 提示：本阶段已写 Chroma 向量；如需实体/关系，再跑 `localbrain mine run`")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
