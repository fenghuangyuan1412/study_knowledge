# -*- coding: utf-8 -*-
"""
本地知识库 Web 问答后端（直连 localbrain，支持多知识库切换）。

每个知识库 = localbrain 一份独立配置/数据（见 PROFILES），互不干扰：
  - ai-software-testing : ~/.localbrain/config.yaml        -> ~/.knowledge-base
  - maoxuan             : ~/.localbrain/config-maoxuan.yaml -> ~/.knowledge-base-maoxuan

能力（自动分级）：已配 嵌入+LLM -> RAG；只配嵌入 -> 语义片段；都没有 -> 关键词片段。
用法：python server.py（默认 http://127.0.0.1:18765；PORT/HOST 可覆盖）
"""
from __future__ import annotations

import logging
import os
import re
import time
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

app = FastAPI(title="知识库问答（localbrain）", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# 多知识库配置
# --------------------------------------------------------------------------
PROFILES: Dict[str, dict] = {
    "ai-software-testing": {
        "label": "AI 软件测试",
        "config": os.path.expanduser("~/.localbrain/config.yaml"),
    },
    "maoxuan": {
        "label": "毛选",
        "config": os.path.expanduser("~/.localbrain/config-maoxuan.yaml"),
    },
}
DEFAULT_KB = "ai-software-testing"

_kb_cache: Dict[str, dict] = {}


def _cfg(kb: str):
    """返回某知识库的 localbrain 配置对象（惰性加载）。"""
    info = PROFILES.get(kb)
    if info is None:
        raise KeyError(kb)
    if kb not in _kb_cache or _kb_cache[kb].get("cfg") is None:
        from kb.config import Config
        _kb_cache.setdefault(kb, {})["cfg"] = Config(Path(info["config"]))
    return _kb_cache[kb]["cfg"]


def _keys_ok(cfg) -> tuple:
    """返回 (embedding 已配 key, llm 已配 key)。空值 / ${ENV} 视为未配置。"""

    def ok(section: str) -> bool:
        s = cfg.get(section, {}) or {}
        raw = s.get("api_key")
        if raw is None:
            return False
        v = str(raw).strip()
        return bool(v) and not v.startswith("${")

    return ok("embedding"), ok("llm")


def _data_dir(cfg) -> Path:
    return Path(os.path.expanduser(str(cfg.data_dir)))


def _count_items(cfg) -> int:
    try:
        d = _data_dir(cfg) / "1_collect"
        if not d.exists():
            return 0
        return sum(1 for _ in d.rglob("*.md"))
    except Exception:  # noqa: BLE001
        return -1


def _rag_for(kb: str):
    """按知识库构造 RAGQuery；失败每 8s 自动重试（自愈）。"""
    cfg = _cfg(kb)
    emb_ok, llm_ok = _keys_ok(cfg)
    if not (emb_ok and llm_ok):
        _kb_cache[kb]["rag"] = None
        return None
    entry = _kb_cache.setdefault(kb, {})
    rag = entry.get("rag")
    if rag is None and time.time() - entry.get("last_try", 0.0) > 8.0:
        entry["last_try"] = time.time()
        try:
            from kb.query.rag import RAGQuery
            rag = RAGQuery(cfg)
            entry["rag"] = rag
            entry.pop("err", None)
        except Exception as e:  # noqa: BLE001
            log.exception("RAGQuery init failed (kb=%s)", kb)
            entry["rag"] = None
            entry["err"] = str(e)
    return rag


def _keyword_search(cfg, q: str, limit: int):
    from kb.query.keyword_search import KeywordSearch
    kw = KeywordSearch(data_dir=str(_data_dir(cfg)))
    return kw.search(keywords=q, limit=limit)


def _read_title(meta: dict, fallback: str, cfg) -> str:
    """从入库文件 frontmatter 读取 title。"""
    fp = meta.get("file_path") or meta.get("id")
    try:
        p = Path(str(fp))
        if not p.is_absolute():
            p = _data_dir(cfg) / str(fp)
        if p.exists():
            head = p.read_text(encoding="utf-8", errors="ignore")[:2000]
            m = re.search(r"^title:\s*[\"']?(.*?)[\"']?\s*$", head, re.M)
            if m and m.group(1).strip():
                return m.group(1).strip()
    except Exception:  # noqa: BLE001
        pass
    return str(fallback)


def _to_source_list(items, cfg) -> list:
    out = []
    for s in items or []:
        meta = s.metadata or {}
        fallback = (meta.get("original_filename") or meta.get("file_path") or s.id)
        title = (meta.get("title") or _read_title(meta, Path(str(fallback)).stem or s.id, cfg))
        # localbrain 写入 Chroma 时 tags 为逗号拼接字符串，统一规范成数组
        raw_tags = meta.get("tags", [])
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, (list, tuple)):
            tags = [str(t) for t in raw_tags]
        else:
            tags = []
        out.append({
            "id": s.id,
            "title": str(title),
            "source": str(meta.get("source", "")),
            "score": round(float(getattr(s, "score", 0) or 0), 3),
            "content": (getattr(s, "content", "") or "")[:600],
            "tags": tags,
        })
    return out


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------
@app.get("/api/status")
def status():
    kbs = []
    error = None
    for kb, info in PROFILES.items():
        try:
            cfg = _cfg(kb)
            emb = cfg.get("embedding", {}) or {}
            llm = cfg.get("llm", {}) or {}
            emb_ok, llm_ok = _keys_ok(cfg)
            rag = _rag_for(kb)
            kbs.append({
                "id": kb,
                "label": info["label"],
                "items": _count_items(cfg),
                "modes": {
                    "rag": bool(rag is not None and getattr(rag, "llm_available", False)),
                    "semantic": emb_ok,
                    "keyword": True,
                },
                "embedding": {"provider": emb.get("provider"), "model": emb.get("model")},
                "llm": {"provider": llm.get("provider"), "model": llm.get("model")},
                "hint": None if (emb_ok and llm_ok) else "未配置可用 key：当前为关键词检索模式",
            })
        except Exception as e:  # noqa: BLE001
            error = error or str(e)
            kbs.append({"id": kb, "label": info["label"], "items": -1,
                        "modes": {"rag": False, "semantic": False, "keyword": False},
                        "embedding": {}, "llm": {}, "hint": "配置加载失败：%s" % e})
    return {
        "engine": "localbrain",
        "default_kb": DEFAULT_KB,
        "kbs": kbs,
        "error": error,
    }


class AskIn(BaseModel):
    question: str
    kb: Optional[str] = None
    top_k: int = 6


@app.post("/api/ask")
def ask(body: AskIn):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    kb = body.kb or DEFAULT_KB
    if kb not in PROFILES:
        raise HTTPException(status_code=400, detail=f"未知知识库: {kb}")
    top_k = max(1, min(body.top_k, 10))

    cfg = _cfg(kb)
    emb_ok, llm_ok = _keys_ok(cfg)

    # 模式一：RAG（query_with_fallback 内部已做语义/关键词降级）
    if emb_ok and llm_ok:
        rag = _rag_for(kb)
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
                        "sources": _to_source_list(r.sources, cfg),
                        "question": q, "kb": kb}
            except Exception as e:  # noqa: BLE001
                log.warning("RAG 查询失败(kb=%s)，降级关键词检索: %s", kb, e)

    # 模式二/三：关键词检索
    try:
        results = _keyword_search(cfg, q, top_k)
    except Exception as e:  # noqa: BLE001
        log.exception("keyword search failed (kb=%s)", kb)
        raise HTTPException(status_code=500, detail=f"关键词检索失败：{e}")
    if results:
        answer = ("[关键词检索] 找到 " + str(len(results)) + " 条相关片段"
                  + ("" if (emb_ok and llm_ok) else "（未配置 AI 服务，暂不生成总结）"))
        return {"mode": "keyword", "answer": answer,
                "sources": _to_source_list(results, cfg),
                "question": q, "kb": kb}
    return {"mode": "none", "answer": "知识库中未找到与问题相关的内容，换个说法试试。",
            "sources": [], "question": q, "kb": kb}


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
