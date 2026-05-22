import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

from datetime import datetime  # noqa: E402

import streamlit as st  # noqa: E402

from components import (  # noqa: E402
    POPULAR_CHAT,
    POPULAR_EMBED,
    badge,
    empty_state,
    fmt_bytes,
    inject_global_css,
    page_header,
    run_pull,
    sidebar_brand,
)
from shared.llm import get_endpoints, get_provider, resolve  # noqa: E402

st.set_page_config(page_title="Ollama · LLM Studio", page_icon="🦙", layout="wide")
inject_global_css()
sidebar_brand()

# Pick endpoint via ?endpoint=<slug> query param (deep-linked from Settings).
# Defaults to the first enabled ollama endpoint, else env-based.
def _pick_ollama_endpoint():
    slug = st.query_params.get("endpoint")
    if slug:
        ep = get_endpoints().get(slug)
        if ep and ep.provider_kind == "ollama":
            return ep
    for ep in get_endpoints().list():
        if ep.provider_kind == "ollama" and ep.enabled:
            return ep
    return None


_active_ep = _pick_ollama_endpoint()
if _active_ep is not None:
    try:
        ollama = resolve(_active_ep, model="-")
    except Exception:
        ollama = get_provider("ollama", model="-")
else:
    ollama = get_provider("ollama", model="-")

healthy = ollama.health()

_ep_label = _active_ep.name if _active_ep else "기본"
page_header(
    "🦙",
    "Ollama",
    f"{_ep_label} · `{ollama.base_url}` — 로컬·원격 Ollama 서버의 모델을 관리합니다.",
)


# ---------- helpers ----------
def fmt_dt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16] if iso else "-"


@st.cache_data(ttl=30, show_spinner=False)
def cached_installed() -> list[dict]:
    try:
        return ollama.list_installed()
    except Exception:
        return []


def refresh_models():
    cached_installed.clear()


# ---------- server status ----------
with st.container(border=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        st.markdown(
            f"<div style='display:flex;gap:8px;align-items:center'>"
            f"<span style='font-weight:600'>서버</span>"
            f"<code>{ollama.base_url}</code>"
            f"{badge('연결됨', 'ok') if healthy else badge('연결 불가', 'err')}"
            f"</div>",
            unsafe_allow_html=True,
        )
    c2.metric("설치된 모델", len(cached_installed()))
    if c3.button("🔄 새로고침", use_container_width=True):
        refresh_models()
        st.rerun()

if not healthy:
    st.error(
        "Ollama 서버에 연결할 수 없습니다. "
        "[설치 가이드](https://ollama.com/download) 를 확인하거나 `OLLAMA_BASE_URL` 을 점검하세요."
    )


# ---------- installed models ----------
installed = cached_installed()
installed_names = {m["name"] for m in installed}

st.markdown("##### 📦 설치된 모델")
if not installed:
    empty_state(
        icon="📦",
        title="설치된 모델이 없습니다",
        hint="아래 ‘인기 모델’ 에서 원클릭으로 받거나, ‘직접 입력’ 탭을 이용하세요.",
    )
else:
    for m in installed:
        with st.container(border=True):
            c = st.columns([4, 1.5, 1.5, 1.5, 2, 0.8])
            c[0].markdown(f"**`{m['name']}`**")
            c[0].caption(m.get("family", "") or "—")
            c[1].caption("크기")
            c[1].write(fmt_bytes(m["size"]))
            c[2].caption("파라미터")
            c[2].write(m["param_size"] or "—")
            c[3].caption("양자화")
            c[3].write(m["quant"] or "—")
            c[4].caption("수정일")
            c[4].write(fmt_dt(m["modified_at"]))
            if c[5].button("🗑️", key=f"del_{m['name']}", use_container_width=True, help="삭제"):
                try:
                    ollama.delete_model(m["name"])
                    refresh_models()
                    st.toast(f"🗑️ {m['name']} 삭제", icon="🦙")
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 실패: {e}")


# ---------- download ----------
st.markdown("##### ⬇️ 모델 다운로드")
tab_chat, tab_embed, tab_manual = st.tabs(["💬 채팅 모델", "🧮 임베딩 모델", "✍️ 직접 입력"])


def render_picks(picks: list[dict], tab_key: str):
    for p in picks:
        with st.container(border=True):
            c = st.columns([3.5, 1.2, 4.5, 1.8])
            c[0].markdown(f"**`{p['name']}`**")
            c[1].markdown(badge(p["size"], "info"), unsafe_allow_html=True)
            c[2].caption(p["desc"])
            if p["name"] in installed_names:
                c[3].markdown(badge("✅ 설치됨", "ok"), unsafe_allow_html=True)
            else:
                if c[3].button("⬇️ Pull", key=f"pull_{tab_key}_{p['name']}", use_container_width=True):
                    if run_pull(ollama, p["name"]):
                        refresh_models()
                        st.rerun()


with tab_chat:
    render_picks(POPULAR_CHAT, "chat")
    st.caption("더 많은 모델: [ollama.com/library](https://ollama.com/library)")

with tab_embed:
    render_picks(POPULAR_EMBED, "embed")

with tab_manual:
    with st.form("manual_pull"):
        name = st.text_input(
            "모델 이름",
            placeholder="예: llama3.1:70b · qwen2.5:14b · 사용자/모델명 …",
        )
        submitted = st.form_submit_button("⬇️ Pull", use_container_width=True)
    if submitted and name:
        if name in installed_names:
            st.warning(f"`{name}` 은(는) 이미 설치되어 있습니다.")
        else:
            if run_pull(ollama, name):
                refresh_models()
                st.rerun()
