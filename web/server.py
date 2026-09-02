# -*- coding: utf-8 -*-
"""
本地知识库 Web 问答后端（直连 localbrain）。

能力（自动分级）：
  - 已配置 嵌入+LLM（DashScope / new-api / Ollama） -> RAG 生成式回答（query_with_fallback）
  - 已配置 嵌入、未配 LLM                        -> 语义检索片段
  - 均未配置                                      -> 本地关键词检索片段（无需任何 key）
运行环境：必须使用安装了 localbrain 的 Python（见 run.ps1 自动定位）。
用法：  python server.py            # 默认 http://127.0.0.1:18765
环境：  PORT / HOST 可覆盖
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kb-web")

app = FastAPI(title="知识库问答（localbrain）", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_config_cache: Dict[str, Any] = {}


def _config():
    if "cfg" not in _config_cache:
        from kb.config import Config
        _config_cache["cfg"] = Config()  # 默认 ~/.localbrain/config.yaml，可用 KB_CONFIG_PATH 覆盖
    return _config_cache["cfg"]


def _service_keys() -> tuple:
    """返回 (embedding 已配 key, llm 已配 key)。空值 / ${ENV} 占位视为未配置。"""
    try:
        cfg = _config()

        def ok(section: str) -> bool:
            s = cfg.get(section, {}) or {}
            raw = s.get("api_key")
            if raw is None:
                return False
            v = str(raw).strip()
            return bool(v) and not v.startswith("${")

        return ok("embedding"), ok("llm")
    except Exception:  # noqa: BLE001
        return False, False


_rag_cache: Dict[str, Any] = {}


def _get_rag():
    """仅在嵌入+LLM 都配好时才构造 RAGQuery（避免空 key 触发无谓的远端调用）。"""
    emb_ok, llm_ok = _service_keys()
    if not (emb_ok and llm_ok):
        _rag_cache["rag"] = None
        return None
    if "rag" not in _rag_cache or _rag_cache.get("rag") is None:
        try:
            from kb.query.rag import RAGQuery
            _rag_cache["rag"] = RAGQuery(_config())
        except Exception as e:  # noqa: BLE001
            log.exception("RAGQuery init failed")
            _rag_cache["rag"] = None
            _rag_cache["err"] = str(e)
    return _rag_cache.get("rag")


def _count_items(config) -> int:
    try:
        d = Path(os.path.expanduser(str(config.data_dir))) / "1_collect"
        if not d.exists():
            return 0
        return sum(1 for _ in d.rglob("*.md"))
    except Exception:  # noqa: BLE001
        return -1


def _read_title(meta: dict, fallback: str) -> str:
    """从入库文件 frontmatter 读取 title（keyword 检索的 metadata 里没有标题时用）。"""
    fp = meta.get("file_path") or meta.get("id")
    try:
        p = Path(str(fp))
        if not p.is_absolute():
            p = Path(os.path.expanduser(str(_config().data_dir))) / str(fp)
        if p.exists():
            head = p.read_text(encoding="utf-8", errors="ignore")[:2000]
            m = re.search(r"^title:\s*[\"']?(.*?)[\"']?\s*$", head, re.M)
            if m and m.group(1).strip():
                return m.group(1).strip()
    except Exception:  # noqa: BLE001
        pass
    return str(fallback)


def _to_source_list(items) -> list:
    out = []
    for s in items or []:
        meta = s.metadata or {}
        fallback = (meta.get("original_filename") or meta.get("file_path") or s.id)
        title = (meta.get("title") or _read_title(meta, Path(str(fallback)).stem or s.id))
        out.append({
            "id": s.id,
            "title": str(title),
            "source": str(meta.get("source", "")),
            "score": round(float(getattr(s, "score", 0) or 0), 3),
            "content": (getattr(s, "content", "") or "")[:600],
            "tags": meta.get("tags", []),
        })
    return out


@app.get("/api/status")
def status():
    try:
        cfg = _config()
    except Exception as e:  # noqa: BLE001
        return {"engine": "localbrain", "items": -1,
                "modes": {"rag": False, "semantic": False, "keyword": False},
                "embedding": {}, "llm": {}, "error": str(e), "hint": None}
    emb = cfg.get("embedding", {}) or {}
    llm = cfg.get("llm", {}) or {}
    emb_ok, llm_ok = _service_keys()
    rag = _get_rag()
    modes = {
        "rag": bool(rag is not None and getattr(rag, "llm_available", False)),
        "semantic": emb_ok,
        "keyword": True,
    }
    hint = None
    if not (emb_ok and llm_ok):
        hint = ("尚未配置可用的嵌入/大模型 key，当前为关键词检索模式。"
                "把 key 写入 ~/.localbrain/config.yaml（仓库外文件）后重启服务，即可升级为语义检索/RAG 问答。")
    return {
        "engine": "localbrain",
        "items": _count_items(cfg),
        "modes": modes,
        "embedding": {"provider": emb.get("provider"), "model": emb.get("model")},
        "llm": {"provider": llm.get("provider"), "model": llm.get("model")},
        "error": None,
        "hint": hint,
    }


class AskIn(BaseModel):
    question: str
    top_k: int = 6


def _keyword_search(q: str, limit: int):
    from kb.query.keyword_search import KeywordSearch
    kw = KeywordSearch(data_dir=str(_config().data_dir))
    return kw.search(keywords=q, limit=limit)


@app.post("/api/ask")
def ask(body: AskIn):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    top_k = max(1, min(body.top_k, 10))
    emb_ok, llm_ok = _service_keys()

    # 模式一：嵌入+LLM 齐备 -> RAG（内部已做语义/关键词降级）
    if emb_ok and llm_ok:
        rag = _get_rag()
        if rag is not None:
            try:
                r = rag.query_with_fallback(q, top_k=top_k)
                answer = (r.answer or "").strip()
                mode = "rag"
                if answer.startswith("[LLM unavailable]"):
                    mode = "semantic"
                elif answer.startswith("[LLM and semantic search unavailable]"):
                    mode = "keyword"
                elif "No relevant information" in answer or "couldn't find relevant" in answer:
                    mode = "none"
                elif answer.startswith("Query failed"):
                    mode = "error"
                return {"mode": mode, "answer": answer,
                        "sources": _to_source_list(r.sources), "question": q}
            except Exception as e:  # noqa: BLE001
                log.warning("RAG 查询失败，降级关键词检索: %s", e)

    # 模式二/三：关键词检索（无需 key；或 RAG 失败后的兜底）
    try:
        results = _keyword_search(q, top_k)
    except Exception as e:  # noqa: BLE001
        log.exception("keyword search failed")
        raise HTTPException(status_code=500, detail=f"关键词检索失败：{e}")
    if results:
        answer = ("[关键词检索] 找到 " + str(len(results)) + " 条相关片段"
                  + ("" if (emb_ok and llm_ok) else "（未配置 AI 服务，暂不生成总结）"))
        return {"mode": "keyword", "answer": answer,
                "sources": _to_source_list(results), "question": q}
    return {"mode": "none", "answer": "知识库中未找到与问题相关的内容，换个说法试试。",
            "sources": [], "question": q}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


if __name__ == "__main__":
    try:
        import kb  # noqa: F401
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 当前 Python 环境缺少 localbrain(kb) 模块：{e}\n"
              f"请改用 web\\run.ps1 启动（会自动使用 localbrain 的 Python）。")
        raise SystemExit(1)
    import uvicorn
    port = int(os.environ.get("PORT", "18765"))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"知识库问答服务: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
