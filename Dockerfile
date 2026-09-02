# 本地知识库问答站（web/server.py + localbrain 引擎）容器化镜像
# 注意：不打包个人知识内容与模型；内容用 ./kb:/kb-in 挂载，向量数据存卷 kb-data。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PORT=18765 \
    HOST=0.0.0.0

WORKDIR /app

# 安装 localbrain 引擎（Python 包，来自 GitHub）
RUN pip install --no-cache-dir \
    "localbrain @ git+https://github.com/agent-creativity/agentic-local-brain.git"

# 拷贝问答站（前端页面 + 后端 + docker 辅助脚本）
COPY web/ /app/web/
COPY web/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 打 think 透传补丁（幂等）：qwen3 类"思考模型"默认把正文放 thinking 字段，
# 需 llm.think=false 才输出 content；见 web/README.md 运维备忘。
RUN python - <<'PY'
from pathlib import Path
import kb
rag = Path(kb.__file__).resolve().parent / "query" / "rag.py"
src = rag.read_text(encoding="utf-8")
needle = '            if self.api_base:\n                kwargs["api_base"] = self.api_base\n'
patch = needle + '''
            # [kb-docker] pass-through optional params (e.g. think=False for qwen3-style models)
            try:
                _think = self.config.get("llm.think")
                if _think is not None:
                    kwargs["think"] = bool(_think)
            except Exception:
                pass
'''
if "think" not in src.split("_call_litellm", 1)[1][:3000] and needle in src:
    rag.write_text(src.replace(needle, patch), encoding="utf-8")
    print("[kb] think pass-through patch applied")
else:
    print("[kb] patch already present or needle missing; skip")
PY

EXPOSE 18765
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "/app/web/server.py"]
