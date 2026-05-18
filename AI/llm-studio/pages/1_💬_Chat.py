import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import time  # noqa: E402
from datetime import datetime  # noqa: E402

import streamlit as st  # noqa: E402

from components import empty_state, inject_global_css, page_header, sidebar_brand  # noqa: E402
from shared.llm import Message, get_provider, list_providers  # noqa: E402

st.set_page_config(page_title="Chat · LLM Studio", page_icon="💬", layout="wide")
inject_global_css()
sidebar_brand()

page_header("💬", "Chat", "Provider 와 모델을 골라 대화하세요. 결과는 마크다운으로 저장 가능합니다.")


# ---------- model discovery ----------
@st.cache_data(ttl=300, show_spinner="모델 리스트 조회 중…")
def fetch_models(provider_name: str) -> tuple[list[str], str | None]:
    try:
        llm = get_provider(provider_name, model="-")
        return list(llm.list_models()), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


# ---------- sidebar ----------
with st.sidebar:
    st.markdown("##### 모델 설정")
    providers = list_providers()
    provider_name = st.selectbox(
        "Provider",
        providers,
        index=providers.index("ollama") if "ollama" in providers else 0,
        label_visibility="visible",
    )

    c1, c2 = st.columns([4, 1])
    c1.caption("Model")
    if c2.button("🔄", help="새로고침", use_container_width=True, key="refresh_models"):
        fetch_models.clear()
        st.rerun()

    models, err = fetch_models(provider_name)
    if err:
        st.warning(f"리스트 조회 실패\n\n```\n{err}\n```")
        model = st.text_input("Model (수동)", value="", label_visibility="collapsed")
    elif not models:
        st.info("사용 가능한 모델이 없습니다.")
        model = st.text_input("Model (수동)", value="", label_visibility="collapsed")
    else:
        key = f"selected_model__{provider_name}"
        prev = st.session_state.get(key)
        idx = models.index(prev) if prev in models else 0
        model = st.selectbox("Model", models, index=idx,
                             key=f"select_{provider_name}", label_visibility="collapsed")
        st.session_state[key] = model

    st.divider()
    st.markdown("##### 프롬프트")
    system = st.text_area(
        "System prompt",
        value="You are a helpful assistant.",
        height=100,
        label_visibility="collapsed",
    )

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("🆕 새 대화", use_container_width=True):
        st.session_state.pop("chat_messages", None)
        st.session_state.pop("last_stats", None)
        st.rerun()
    has_msgs = bool(st.session_state.get("chat_messages"))
    if has_msgs:
        md = f"# Chat — {datetime.now():%Y-%m-%d %H:%M}\n\n"
        md += f"_provider: `{provider_name}` · model: `{model}`_\n\n"
        for m in st.session_state.get("chat_messages", []):
            md += f"## {m['role']}\n\n{m['content']}\n\n"
        c2.download_button(
            "💾 .md 저장",
            data=md.encode("utf-8"),
            file_name=f"chat_{datetime.now():%Y%m%d_%H%M%S}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    else:
        c2.button("💾 .md 저장", disabled=True, use_container_width=True)


# ---------- state ----------
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# ---------- conversation area ----------
if not st.session_state.chat_messages:
    empty_state(
        icon="💬",
        title="대화를 시작하세요",
        hint=f"`{provider_name}` · `{model or '모델 미선택'}` · 사이드바에서 변경 가능",
    )
else:
    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    stats = st.session_state.get("last_stats")
    if stats:
        c1, c2, c3 = st.columns(3)
        c1.metric("응답 시간", f"{stats['elapsed']:.1f}s")
        c2.metric("출력 토큰", stats.get("output_tokens") or "—")
        c3.metric("청크 수", stats["chunks"])

# ---------- input ----------
user_input = st.chat_input(
    f"{provider_name} / {model or '모델 미선택'} 에게 보낼 메시지…"
)
if user_input:
    if not model:
        st.error("모델을 먼저 선택하세요.")
        st.stop()

    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    try:
        llm = get_provider(provider_name, model=model)
    except Exception as e:
        st.error(f"Provider 초기화 실패: {e}")
        st.stop()

    msgs: list[Message] = []
    if system.strip():
        msgs.append(Message(role="system", content=system))
    msgs += [Message(role=m["role"], content=m["content"]) for m in st.session_state.chat_messages]

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full = ""
        chunks = 0
        t0 = time.time()
        last_raw = None
        try:
            for chunk in llm.stream(msgs):
                full += chunk.delta
                chunks += 1
                last_raw = chunk.raw
                placeholder.markdown(full + " ▌")
            placeholder.markdown(full)
        except Exception as e:
            st.error(f"호출 실패: {e}")
            st.stop()

    elapsed = time.time() - t0
    out_tokens = (last_raw or {}).get("eval_count") if isinstance(last_raw, dict) else None
    st.session_state.last_stats = {
        "elapsed": elapsed, "chunks": chunks, "output_tokens": out_tokens,
    }
    st.session_state.chat_messages.append({"role": "assistant", "content": full})
    st.rerun()
