# -*- coding: utf-8 -*-
"""
毛选分卷「内容总结」生成管线（map-reduce + 断点续跑）。

为什么这么做：9B 本地模型上下文有限，而单篇最长达 141KB。
先用 map 把长文分段压成要点，再用 reduce 合成一篇结构化总结，
写进 kb/maoxuan/batch-<N>/items/，供向量库检索、供本地模型阅读。

用法：
    python mao_summarize.py --volume 1              # 生成第一卷
    python mao_summarize.py --volume 1 --only 01-09 # 只跑一篇（调试）
    python mao_summarize.py --volume 1 --reduce-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# 毛选全文语料（本地 skill 目录，不入 git）；可用 --src 覆盖
SRC_DIR = Path(r"C:\Users\Administrator\.agents\skills\mao-selected-works\data")
# 产出目录：kb/maoxuan/batch-<卷+1>/items/
OUT_ROOT = REPO / "kb" / "maoxuan"
# 断点续跑状态（临时目录，不入 git）
STATE_DIR = HERE / ".runtime" / "_mao_sum"
OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen3.5:9b"
NUM_CTX = 8192
CHUNK = 2400          # 每段目标字数（中文按字符计）
OVERLAP = 150
RETRIES = 3

STATE_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(msg, flush=True)


def llm(prompt: str, num_predict: int = 900) -> str:
    """调本地 Ollama。think=false：qwen3 类模型默认把正文放 thinking 字段。"""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"num_ctx": NUM_CTX, "temperature": 0.3, "num_predict": num_predict},
    }
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(
                OLLAMA,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=900) as r:
                out = json.loads(r.read().decode())
            txt = (out.get("response") or "").strip()
            if txt:
                return txt
            last = "empty response"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            try:
                last += " | " + e.read().decode()[:300]  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        if attempt < RETRIES:
            log(f"    retry {attempt}/{RETRIES - 1} after: {last}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"LLM failed after {RETRIES} tries: {last}")


def load_state(name: str) -> dict:
    p = STATE_DIR / f"{name}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_state(name: str, data: dict) -> None:
    (STATE_DIR / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def clean_body(md: str) -> str:
    """去掉脚注定义、空脚注标记，压掉多余空行。"""
    md = re.sub(r"(?m)^\[\^\d+\]:\s*$", "", md)
    md = re.sub(r"\[\^\d+\]", "", md)
    md = re.sub(r"(?m)^\s*注\s*释\s*$", "\n## 注释\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def split_chunks(text: str) -> list[str]:
    """按段落边界切块，避免把一句话劈开。"""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur, size = [], [], 0
    for p in paras:
        if size + len(p) > CHUNK and cur:
            chunks.append("\n\n".join(cur))
            tail = cur[-1][-OVERLAP:] if len(cur[-1]) > OVERLAP else cur[-1]
            cur, size = [tail], len(tail)
        cur.append(p)
        size += len(p)
    if cur:
        chunks.append("\n\n".join(cur))
    chunks = [c for c in chunks if len(c) > 200]
    return chunks or [text[:CHUNK]]


MAP_PROMPT = """你在为《毛泽东选集》做读书提要。下面是一篇文章的第 {i}/{n} 段原文。

要求：**只依据原文**，不要添加原文没有的内容，不要评论。
用中文输出这段的要点，格式：
- 本段讨论的问题：
- 主要论点（2-5 条，每条一句话）：
- 关键概念/提法（列出原文用词）：
- 值得记的原句（1-2 句，必须是原文原话，用引号）：
如果本段只是注释/名单/礼节性文字，就一句话说明"本段为<性质>，无核心论点"。

原文：
---
{chunk}
---
"""

REDUCE_PROMPT = """你在为《毛泽东选集》做读书提要。下面是同一篇文章各段落的要点汇总。

请**只依据这些要点**合成一份结构化的中文内容总结。
**禁止编造**：凡是这些要点里没有出现的内容，一律不要写；不确定就略过。
严格按下面的 Markdown 结构输出（不要加其它标题、不要写"总结如下"之类的话）：

## 一句话摘要

（一两句话讲清这篇文章写了什么、要解决什么问题）

## 写作背景与针对的问题

（3-5 条，只写要点里提到的）

## 主要内容

（分点，5-8 条，每条先给结论再补一句解释；这是给读者快速掌握全文用的）

## 关键概念与提法

（只列原文里**真实出现**的说法、判断、口号，用原文用词。
每条写成：词条 —— 原文中与它直接相关的一句话（照抄原句）。
**不要自己解释词义**；原文里没有对应句子的，就只写词条本身，不要臆测含义）

## 结论与影响

（2-4 条，只写各段要点里明确出现过的结论；没有就写"（提要未涉及）"）

## 短句引文

> （2-3 句原文原话，必须来自各段要点里引到的原句；没有就写"（本段提要未摘录原句）"）

文章标题：{title}
各段要点：
---
{joined}
---
"""


def sanitize(summary: str) -> str:
    """清掉模型把 map 阶段格式回显进正文的痕迹。

    典型泄漏：`悲观论调 —— 本段讨论的问题：分析当时党内...`
    我们要的是词条 + 原文原句，不是任务说明的回声。
    """
    out = []
    for line in summary.split("\n"):
        # 去掉行内泄漏的字段名前缀
        line = re.sub(r"本段讨论的问题[：:]\s*", "", line)
        line = re.sub(r"主要论点（[^）]*）[：:]\s*", "", line)
        line = re.sub(r"关键概念/提法[：:]\s*", "", line)
        line = re.sub(r"值得记的原句[：:]\s*", "", line)
        line = re.sub(r"^\s*-\s*本段为[^\n]*无核心论点[^\n]*$", "", line)
        line = re.sub(r"[ \t]{2,}", " ", line).rstrip()
        # 清掉只剩「词条 ——」后面没内容的残行
        if re.match(r"^\s*[-*]?\s*[^—\n]{1,20}——\s*$", line):
            continue
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_item(title: str, volume: int, order: str, year: str, summary: str) -> str:
    topic_tag = title.replace("《", "").replace("》", "")[:12]
    fm = [
        "---",
        f"title: {title}：内容总结",
        f"source_url: 《毛泽东选集》第{'一二三四五六七'[volume - 1]}卷·{title}（人民出版社）",
        f"author: 毛泽东（{year}）；本笔记由本地模型依据原文分段归纳整理",
        "source_type: book-summary",
        "batch: 2",
        f"order: {order}",
        f"collected_at: {time.strftime('%Y-%m-%d')}",
        f"tags: [毛选, 第{'一二三四五六七'[volume - 1]}卷, {topic_tag}, 内容总结]",
        "---",
        "",
    ]
    body = sanitize(summary).strip()
    if not body.startswith("## 一句话摘要"):
        body = "## 一句话摘要\n\n" + body
    tail = [
        "",
        "## 来源",
        "",
        f"- 毛泽东：《{title}》（{year}），载《毛泽东选集》第{'一二三四五六七'[volume - 1]}卷，人民出版社。",
        "- 说明：本文为分段归纳的内容总结（非原文全文）；引用原文时请回原书核对。",
        "",
    ]
    return "\n".join(fm) + "\n" + body + "\n" + "\n".join(tail)


CN_DIGITS = {"〇": 0, "○": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3,
             "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def year_of(md: str) -> str:
    """从正文里取写作年份。原文多写作『一九三三年』，必须转成阿拉伯数字。"""
    for m in re.finditer(r"([〇○零一二三四五六七八九]{4})\s*年", md):
        digits = "".join(str(CN_DIGITS[c]) for c in m.group(1))
        if digits.startswith(("18", "19", "20")):
            return digits
    m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", md)
    return m.group(1) if m else "年份待考"


MID_PROMPT = """你在为《毛泽东选集》的《{title}》做读书提要。下面是这篇文章【第 {i} 组 / 共 {n} 组】的段落要点。

请把这些要点**合并压缩**成一组更凝练的要点，只保留实质内容，**不要编造**：
- 本组涉及的问题：
- 主要论点（3-6 条，每条一句话，尽量保留原文用词）：
- 值得记的原句（1-3 句，必须是原文原话）：

要点：
---
{joined}
---
"""

# 单次 reduce 的输入上限（字符）。超过就必须分层，否则会超出 num_ctx 被截断，
# 表现为输出在「## 主要内容」中途断掉、后面的章节整段消失。
MAX_REDUCE_CHARS = 6000


def reduce_notes(title: str, joined: str, chunks: int) -> str:
    """把各段要点合成结构化总结；要点太长时分两层做，避免上下文被截断。"""
    if len(joined) <= MAX_REDUCE_CHARS:
        log(f"    reduce ({len(joined)} chars of notes)")
        return llm(REDUCE_PROMPT.format(title=title, joined=joined), num_predict=1400)

    # ---- 分层：先分组压缩，再总合成 ----
    items = [b for b in joined.split("\n\n") if b.strip()]
    groups, cur, size = [], [], 0
    for it in items:
        if size + len(it) > MAX_REDUCE_CHARS and cur:
            groups.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(it)
        size += len(it)
    if cur:
        groups.append("\n\n".join(cur))

    log(f"    notes too long ({len(joined)} chars) -> hierarchical reduce over {len(groups)} groups")
    mids = []
    for gi, g in enumerate(groups, 1):
        log(f"    mid-reduce {gi}/{len(groups)} ({len(g)} chars)")
        mids.append(llm(MID_PROMPT.format(i=gi, n=len(groups), title=title, joined=g),
                        num_predict=900))
    merged = "\n\n".join(f"【第{i}组要点】\n{m}" for i, m in enumerate(mids, 1))
    log(f"    final reduce ({len(merged)} chars)")
    return llm(REDUCE_PROMPT.format(title=title, joined=merged), num_predict=1400)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volume", type=int, default=1)
    ap.add_argument("--only", default=None, help="只处理文件名前缀匹配的篇，如 01-09")
    ap.add_argument("--reduce-only", action="store_true", help="跳过 map，直接用已有分段要点合成")
    ap.add_argument("--force", action="store_true", help="已完成的重做")
    args = ap.parse_args()

    prefix = f"{args.volume:02d}-"
    files = sorted(f for f in SRC_DIR.glob(f"{prefix}*.md"))
    if args.only:
        files = [f for f in files if f.name.startswith(args.only)]
    if not files:
        log(f"no source files for volume {args.volume}")
        return 1

    out_dir = OUT_ROOT / f"batch-{1 + args.volume:03d}" / "items"
    out_dir.mkdir(parents=True, exist_ok=True)
    state_name = f"vol{args.volume}"
    state = load_state(state_name)

    log(f"volume {args.volume}: {len(files)} 篇 -> {out_dir}")

    for idx, f in enumerate(files, 1):
        title = re.sub(r"^\d+-\d+-", "", f.stem)
        order = f.name.split("-")[1]
        key = f.name
        log(f"\n[{idx}/{len(files)}] {title}  ({f.stat().st_size // 1024}KB)")

        raw = f.read_text(encoding="utf-8", errors="ignore")
        body = clean_body(raw)
        year = year_of(body)
        chunks = split_chunks(body)

        # setdefault：否则 ent 是游离的新 dict，save_state 永远存不进去（断点续跑失效）
        ent = state.setdefault(key, {})
        if ent.get("done") and not args.force:
            log(f"    skip (already done): {ent.get('output', '')}")
            continue
        ent.setdefault("title", title)
        ent.setdefault("year", year)
        ent.setdefault("order", order)
        ent.setdefault("chunks", len(chunks))
        ent.setdefault("parts", {})

        if not args.reduce_only:
            for i, ch in enumerate(chunks, 1):
                if str(i) in ent["parts"] and ent["parts"][str(i)].strip():
                    continue
                log(f"    map {i}/{len(chunks)} ({len(ch)} chars)")
                ent["parts"][str(i)] = llm(
                    MAP_PROMPT.format(i=i, n=len(chunks), chunk=ch), num_predict=700
                )
                save_state(state_name, state)
        else:
            if not ent["parts"]:
                log("    no cached parts; skip")
                continue

        missing = [i for i in range(1, len(chunks) + 1) if str(i) not in ent["parts"]]
        if missing:
            log(f"    WARNING missing parts {missing}; reducing with what we have")

        joined = "\n\n".join(
            f"【第{i}段要点】\n{ent['parts'][str(i)]}"
            for i in sorted(ent["parts"], key=int)
        )
        summary = reduce_notes(title, joined, len(chunks))

        out = out_dir / f"{args.volume:02d}-{order}-{title}.md"
        out.write_text(build_item(title, args.volume, order, year, summary), encoding="utf-8")
        ent["done"] = True
        ent["output"] = str(out)
        save_state(state_name, state)
        log(f"    -> {out.name}  ({len(summary)} chars)")

    done = sum(1 for v in state.values() if v.get("done"))
    log(f"\nDONE volume {args.volume}: {done}/{len(files)} 篇完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
