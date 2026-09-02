# -*- coding: utf-8 -*-
"""
本地知识库 Web 问答后端（直连 localbrain）。

能力：RAG(生成式回答) -> 语义检索片段 -> 关键词检索片段，三级自动降级。
运行环境：必须使用安装了 localbrain 的 Python（见 run.ps1 自动定位）。
用法：  python server.py            # 默认 http://127.0.0.1:8765
环境：  PORT=8765 HOST=127.0.0.1    # 可覆盖
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kb-web")

app = FastAPI(title="知识库问答（localbrain）", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _config():
    from kb.config import Config
    return Config()  # 默认读取 ~/.localbrain/config.yaml（可用 KB_CONFIG_PATH 覆盖）


_cache: Dict[str, Any] = {}


def _get_rag():
    """惰性构造 RAGQuery；失败记录 error。"""
    if "rag" in _cache:
        return _cache["rag"], _cache.get("error")
    try:
        from kb.query.rag import RAGQuery
        _cache["rag"] = RAGQuery(_config())
        _cache["error"] = None
    except Exception as e:  # noqa: BLE001
        log.exception("RAGQuery init failed")
        _cache["rag"] = None
        _cache["error"] = str(e)
    return _cache["rag"], _cache.get("error")


def _count_items(config) -> int:
    try:
        d = Path(os.path.expanduser(str(config.data_dir))) / "1_collect"
        if not d.exists():
            return 0
        return sum(1 for _ in d.rglob("*.md"))
    except Exception:  # noqa: BLE001
        return -1


@app.get("/api/status")
def status():
    rag, err = _get_rag()
    cfg = None
    try:
        cfg = _config()
    except Exception as e:  # noqa: BLE001
        err = err or str(e)
    emb = (cfg.get("embedding", {}) if cfg else {}) or {}
    llm = (cfg.get("llm", {}) if cfg else {}) or {}
    out = {
        "engine": "localbrain",
        "items": _count_items(cfg) if cfg else -1,
        "modes": {"rag": False, "semantic": False, "keyword": True},
        "embedding": {"provider": emb.get("provider"), "model": emb.get("model")},
        "llm": {"provider": llm.get("provider"), "model": llm.get("model")},
        "error": err,
    }
    if rag is not None:
        out["modes"]["rag"] = bool(getattr(rag, "llm_available", False))
        sem = getattr(rag, "semantic_search", None)
        out["modes"]["semantic"] = bool(sem is not None and getattr(sem, "embedder", None) is not None)
        out["llm"]["provider"] = getattr(rag, "llm_provider", llm.get("provider"))
        out["llm"]["model"] = getattr(rag, "model", llm.get("model"))
    return out


class AskIn(BaseModel):
    question: str
    top_k: int = 6


@app.post("/api/ask")
def ask(body: AskIn):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    rag, err = _get_rag()
    if rag is None:
        raise HTTPException(status_code=503, detail=f"localbrain 引擎不可用：{err}")
    try:
        r = rag.query_with_fallback(q, top_k=max(1, min(body.top_k, 10)))
    except Exception as e:  # noqa: BLE001
        log.exception("query failed")
        raise HTTPException(status_code=500, detail=f"查询失败：{e}")

    answer = (r.answer or "").strip()
    mode = "rag"
    if answer.startswith("[LLM unavailable]"):
        mode = "semantic"
    elif answer.startswith("[LLM and semantic search unavailable]"):
        mode = "keyword"
    elif "No relevant information" in answer:
        mode = "none"
    elif answer.startswith("Query failed"):
        mode = "error"

    sources = []
    for s in (r.sources or []):
        meta = s.metadata or {}
        title = meta.get("title") or Path(str(meta.get("file_path", ""))).stem or s.id
        sources.append({
            "id": s.id,
            "title": title,
            "source": meta.get("source", ""),
            "score": round(float(s.score or 0.0), 3),
            "content": (s.content or "")[:600],
            "tags": meta.get("tags", []),
        })
    return {"mode": mode, "answer": answer, "sources": sources, "question": q}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


if __name__ == "__main__":
    try:
        import kb  # noqa: F401
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 当前 Python 环境缺少 localbrain(kb) 模块：{e}\n"
              f"请改用 web\\run.ps1 启动（会自动使用 localbrain 的 Python）。")
        sys.exit(1)
    import uvicorn
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"知识库问答服务: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
