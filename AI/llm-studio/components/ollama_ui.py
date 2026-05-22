"""Shared Ollama model catalog + pull-progress widget.

Single source of truth for the curated model picks and the streaming
download UI, used by both the Ollama page and the Settings pull dialog.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from .ui import fmt_bytes

# ---------- curated picks ----------
POPULAR_CHAT: list[dict[str, str]] = [
    {"name": "llama3.2:1b",    "size": "1.3GB", "desc": "Llama 3.2 — 초경량, 빠른 응답"},
    {"name": "llama3.2:3b",    "size": "2.0GB", "desc": "Llama 3.2 — 균형형 (추천 시작점)"},
    {"name": "llama3.1:8b",    "size": "4.7GB", "desc": "Llama 3.1 — 표준 사이즈"},
    {"name": "qwen2.5:7b",     "size": "4.7GB", "desc": "Qwen 2.5 — 다국어 우수"},
    {"name": "mistral:7b",     "size": "4.4GB", "desc": "Mistral — 코드 강점"},
    {"name": "gemma2:2b",      "size": "1.6GB", "desc": "Google Gemma 2"},
    {"name": "phi3:mini",      "size": "2.3GB", "desc": "Microsoft Phi-3 Mini"},
    {"name": "deepseek-r1:7b", "size": "4.7GB", "desc": "DeepSeek R1 — 추론 강화"},
]
POPULAR_EMBED: list[dict[str, str]] = [
    {"name": "nomic-embed-text",  "size": "274MB", "desc": "Nomic — 일반 임베딩"},
    {"name": "mxbai-embed-large", "size": "670MB", "desc": "MixedBread — 대형 임베딩"},
]


def run_pull(provider: Any, name: str) -> bool:
    """Stream `ollama pull <name>` into an st.status progress block.

    Returns True on success. `provider` is any object exposing `.pull(name)`
    that yields {"status", "total", "completed"} dicts (the Ollama provider).
    """
    with st.status(f"📥 `{name}` 다운로드 중…", expanded=True) as status:
        progress = st.progress(0.0)
        detail = st.empty()
        try:
            for evt in provider.pull(name):
                s = evt.get("status", "")
                total = evt.get("total")
                completed = evt.get("completed")
                if total and completed:
                    frac = min(completed / total, 1.0)
                    progress.progress(frac)
                    detail.write(
                        f"`{s}` · {fmt_bytes(completed)} / "
                        f"{fmt_bytes(total)} · {frac * 100:.1f}%"
                    )
                else:
                    detail.write(f"`{s}`")
            progress.progress(1.0)
            status.update(label=f"✅ `{name}` 완료", state="complete", expanded=False)
            return True
        except Exception as e:
            status.update(label=f"❌ pull 실패: {e}", state="error")
            return False
