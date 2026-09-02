# -*- coding: utf-8 -*-
"""把挂载目录（含子目录）里的 .md 知识逐条导入 localbrain 知识库。

用法: python kb_import.py <md根目录>
说明:
  - 用 `localbrain collect file add --skip-existing`，已存在的自动跳过、不重复入库；
  - 收集时若模型服务可用会同时写入 Chroma 向量索引（模型未就绪则仅原文入库，
    之后可重跑本脚本并不会补索引 —— 请在模型就绪后执行一次首次导入）。
"""
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/kb-in")
    if not root.exists():
        print(f"[kb] import dir not found: {root}")
        return
    files = sorted(p for p in root.rglob("*.md") if p.is_file())
    if not files:
        print(f"[kb] no .md files under {root}")
        return
    cli = shutil.which("localbrain") or shutil.which("kb")
    if not cli:
        print("[kb] ERROR: localbrain CLI not found")
        sys.exit(1)

    ok = skipped = failed = 0
    for f in files:
        r = subprocess.run(
            [cli, "collect", "file", "add", str(f), "--skip-existing"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        low = out.lower()
        if "duplicate" in low or "already" in low:
            skipped += 1
        elif r.returncode == 0 or "collected" in low or "collecting" in low:
            ok += 1
        else:
            failed += 1
            print(f"[kb] FAIL {f.name}: {out.strip()[-300:]}")
    print(f"[kb] import done: ok={ok} skipped={skipped} failed={failed} (total {len(files)})")


if __name__ == "__main__":
    main()
