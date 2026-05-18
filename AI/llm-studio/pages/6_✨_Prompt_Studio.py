import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import streamlit as st  # noqa: E402

from components import (  # noqa: E402
    badge,
    inject_global_css,
    page_header,
    sidebar_brand,
)
from shared.llm import (  # noqa: E402
    PERSONAS,
    PERSONAS_BY_SLUG,
    enhance_to_system_prompt,
    get_provider,
    list_providers,
)

st.set_page_config(page_title="Prompt Studio · LLM Studio", page_icon="✨", layout="wide")
inject_global_css()
sidebar_brand()

page_header(
    "✨",
    "Prompt Studio",
    "페르소나 라이브러리에서 고르거나, 한 줄 설명을 system prompt 로 향상시켜 Chat 에 적용합니다.",
)


# ============================================================
# sidebar — model for enhancement
# ============================================================
@st.cache_data(ttl=300, show_spinner="모델 리스트 조회 중…")
def fetch_models(provider_name: str) -> tuple[list[str], str | None]:
    try:
        return list(get_provider(provider_name, model="-").list_models()), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


with st.sidebar:
    st.markdown("##### 🤖 향상 작업용 모델")
    providers = list_providers()
    default_idx = (
        providers.index("litellm") if "litellm" in providers
        else providers.index("ollama") if "ollama" in providers
        else 0
    )
    provider_name = st.selectbox("Provider", providers, index=default_idx)

    c1, c2 = st.columns([4, 1])
    c1.caption("Model")
    if c2.button("🔄", help="새로고침", use_container_width=True, key="refresh_studio"):
        fetch_models.clear()
        st.rerun()

    models, err = fetch_models(provider_name)
    if err:
        st.warning(f"리스트 조회 실패\n\n```\n{err}\n```")
        model = st.text_input("Model (수동)", value="", label_visibility="collapsed")
    elif not models:
        model = st.text_input("Model (수동)", value="", label_visibility="collapsed")
    else:
        key = f"studio_model__{provider_name}"
        prev = st.session_state.get(key)
        idx = models.index(prev) if prev in models else 0
        model = st.selectbox("Model", models, index=idx,
                             key=f"studio_select_{provider_name}", label_visibility="collapsed")
        st.session_state[key] = model

    st.caption("향상 작업은 instruct 능력이 좋은 모델 (claude / gpt / qwen2.5+) 권장")


# ============================================================
# state — current prompt being edited
# ============================================================
if "studio_prompt" not in st.session_state:
    st.session_state.studio_prompt = ""
if "studio_persona" not in st.session_state:
    st.session_state.studio_persona = None  # slug of active library persona, or None


# ============================================================
# main layout — left: library, right: editor
# ============================================================
left, right = st.columns([1.1, 2])


# ---------- LEFT: persona library ----------
with left:
    st.markdown("##### 📚 페르소나 라이브러리")
    st.caption("큐레이션된 시스템 프롬프트 — 선택하면 오른쪽 편집기로 불러옵니다.")

    for p in PERSONAS:
        active = st.session_state.studio_persona == p.slug
        with st.container(border=True):
            c1, c2 = st.columns([5, 2])
            c1.markdown(
                f"<div style='font-size:1.1rem'><span style='font-size:1.5rem'>{p.icon}</span>"
                f" <b>{p.name}</b></div>"
                f"<div style='color:#64748B;font-size:0.85rem;margin-top:2px'>{p.description}</div>",
                unsafe_allow_html=True,
            )
            if active:
                c2.markdown(badge("✓ 적용됨", "ok"), unsafe_allow_html=True)
            else:
                if c2.button("불러오기", key=f"load_{p.slug}", use_container_width=True):
                    st.session_state.studio_prompt = p.system_prompt
                    st.session_state.studio_persona = p.slug
                    st.rerun()


# ---------- RIGHT: editor + enhancer ----------
with right:
    st.markdown("##### 📝 System prompt")

    # active persona indicator
    if st.session_state.studio_persona:
        p = PERSONAS_BY_SLUG.get(st.session_state.studio_persona)
        if p:
            st.markdown(
                f"<div style='margin-bottom:8px'>{badge(f'{p.icon} {p.name}', 'info')}"
                f" <span style='color:#64748B;font-size:0.85rem'>· 라이브러리에서 불러옴 (자유롭게 편집 가능)</span></div>",
                unsafe_allow_html=True,
            )

    prompt = st.text_area(
        "system prompt",
        value=st.session_state.studio_prompt,
        height=320,
        key="studio_prompt_editor",
        label_visibility="collapsed",
        placeholder="시스템 프롬프트를 직접 작성하거나, 라이브러리에서 불러오거나, 아래 ✨ 향상 기능을 사용하세요.",
    )
    # keep state in sync
    if prompt != st.session_state.studio_prompt:
        st.session_state.studio_prompt = prompt
        # editing detaches from library
        if st.session_state.studio_persona:
            p = PERSONAS_BY_SLUG.get(st.session_state.studio_persona)
            if p and prompt != p.system_prompt:
                st.session_state.studio_persona = None

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    if c1.button("🆕 비우기", use_container_width=True):
        st.session_state.studio_prompt = ""
        st.session_state.studio_persona = None
        st.rerun()
    if c2.button("💬 Chat 에 적용", type="primary", use_container_width=True,
                 disabled=not prompt.strip()):
        st.session_state["applied_system_prompt"] = prompt
        st.session_state["applied_persona_label"] = (
            f"{PERSONAS_BY_SLUG[st.session_state.studio_persona].icon} "
            f"{PERSONAS_BY_SLUG[st.session_state.studio_persona].name}"
            if st.session_state.studio_persona else None
        )
        st.toast("💬 Chat 페이지의 system prompt 로 적용됨", icon="✨")
    c3.download_button(
        "💾 .md",
        data=prompt.encode("utf-8") if prompt else b"",
        file_name="system_prompt.md",
        mime="text/markdown",
        use_container_width=True,
        disabled=not prompt.strip(),
    )

    st.divider()

    # ---------- enhancement ----------
    st.markdown("##### ✨ 한 줄 설명 → System prompt 로 향상")
    st.caption(
        "어떤 어시스턴트를 원하는지 짧게 적으면 LLM 이 페르소나·전문성·말투·가이드라인을 갖춘 "
        "정식 system prompt 로 확장합니다."
    )
    description = st.text_area(
        "한 줄 설명",
        placeholder="예: 한국어 IT 뉴스 헤드라인을 영어로 매끄럽게 번역하는 어시스턴트",
        height=80,
        key="studio_desc",
        label_visibility="collapsed",
    )
    constraints = st.text_input(
        "추가 제약 (선택)",
        placeholder="예: 출력은 항상 한국어 / 코드 블록 사용 금지 / 정중한 말투",
        key="studio_constraints",
    )

    c1, c2 = st.columns([1.2, 2])
    enhance_clicked = c1.button(
        "✨ 향상",
        type="primary",
        disabled=not (description.strip() and model),
        use_container_width=True,
    )
    if not model:
        c2.caption("모델을 먼저 선택하세요.")

    if enhance_clicked:
        try:
            llm = get_provider(provider_name, model=model)
            with st.spinner(f"`{model}` 로 향상 중…"):
                enhanced = enhance_to_system_prompt(
                    llm,
                    description=description,
                    extra_constraints=constraints,
                )
            st.session_state.studio_prompt = enhanced
            st.session_state.studio_persona = None  # custom now
            st.toast("✅ system prompt 생성됨 — 위 편집기에서 확인", icon="✨")
            st.rerun()
        except Exception as e:
            st.error(f"향상 실패: {type(e).__name__}: {e}")


# ============================================================
# footer hint
# ============================================================
st.divider()
st.caption(
    "💡 적용 후 Chat 페이지로 이동하면 사이드바 System prompt 가 자동으로 채워집니다. "
    "Chat 의 textarea 에서 추가 편집도 가능."
)
