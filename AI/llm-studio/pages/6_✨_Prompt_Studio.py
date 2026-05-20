import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import streamlit as st  # noqa: E402

from components import (  # noqa: E402
    badge,
    inject_global_css,
    page_header,
    render_sidebar,
    sidebar_brand,
)
from shared.llm import enhance_to_system_prompt, resolve  # noqa: E402
from shared.skills import Skill, get_registry  # noqa: E402

st.set_page_config(page_title="Prompt Studio · LLM Studio", page_icon="✨", layout="wide")
inject_global_css()
sidebar_brand()

page_header(
    "✨",
    "Prompt Studio",
    "라이브러리(chat-system 스킬)에서 고르거나, 한 줄 설명을 system prompt 로 향상해 Chat 또는 새 스킬에 저장합니다.",
)


# ============================================================
# sidebar
# ============================================================
state = render_sidebar(
    "prompt-studio",
    kinds=["chat-system", "prompt-enhance"],
    default_system_prompt="",
)


# ============================================================
# state
# ============================================================
if "studio_prompt" not in st.session_state:
    st.session_state.studio_prompt = ""
if "studio_persona" not in st.session_state:
    st.session_state.studio_persona = None  # slug of active library skill


# When a chat-system skill is picked in the sidebar, mirror it into the editor.
if state.skill and state.skill.kind == "chat-system":
    if st.session_state.studio_persona != state.skill.slug:
        st.session_state.studio_prompt = state.skill.system_prompt
        st.session_state.studio_persona = state.skill.slug


registry = get_registry()
library_skills: list[Skill] = registry.by_kind("chat-system")


# ============================================================
# main layout — left: library, right: editor
# ============================================================
left, right = st.columns([1.1, 2])


with left:
    st.markdown("##### 📚 라이브러리 (chat-system 스킬)")
    st.caption("선택하면 오른쪽 편집기로 불러옵니다. 사용자 스킬도 함께 표시됨.")

    for p in library_skills:
        active = st.session_state.studio_persona == p.slug
        with st.container(border=True):
            c1, c2 = st.columns([5, 2])
            lock = " 🔒" if p.readonly else ""
            c1.markdown(
                f"<div style='font-size:1.05rem'>"
                f"<span style='font-size:1.4rem'>{p.icon}</span> "
                f"<b>{p.name}</b>{lock}</div>"
                f"<div style='color:#64748B;font-size:0.83rem;margin-top:2px'>{p.description}</div>",
                unsafe_allow_html=True,
            )
            if active:
                c2.markdown(badge("✓ 적용됨", "ok"), unsafe_allow_html=True)
            else:
                if c2.button("불러오기", key=f"load_{p.slug}", use_container_width=True):
                    st.session_state.studio_prompt = p.system_prompt
                    st.session_state.studio_persona = p.slug
                    st.rerun()


with right:
    st.markdown("##### 📝 System prompt")

    if st.session_state.studio_persona:
        active_skill = registry.get(st.session_state.studio_persona)
        if active_skill:
            st.markdown(
                f"<div style='margin-bottom:8px'>"
                f"{badge(f'{active_skill.icon} {active_skill.name}', 'info')}"
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
    if prompt != st.session_state.studio_prompt:
        st.session_state.studio_prompt = prompt
        # editing detaches from library
        if st.session_state.studio_persona:
            active_skill = registry.get(st.session_state.studio_persona)
            if active_skill and prompt != active_skill.system_prompt:
                st.session_state.studio_persona = None

    c1, c2, c3, c4 = st.columns([1, 1.3, 1.3, 1])
    if c1.button("🆕 비우기", use_container_width=True):
        st.session_state.studio_prompt = ""
        st.session_state.studio_persona = None
        st.rerun()
    if c2.button("💬 Chat 에 적용", type="primary", use_container_width=True,
                 disabled=not prompt.strip()):
        st.session_state["applied_system_prompt"] = prompt
        active = (
            registry.get(st.session_state.studio_persona)
            if st.session_state.studio_persona else None
        )
        st.session_state["applied_persona_label"] = (
            f"{active.icon} {active.name}" if active else None
        )
        # Clear Chat sidebar state so it picks up the new prompt
        st.session_state.pop("sidebar_system__chat", None)
        st.toast("💬 Chat 페이지의 system prompt 로 적용됨", icon="✨")
    if c3.button("💾 스킬로 저장", use_container_width=True, disabled=not prompt.strip()):
        st.session_state["show_save_skill_dialog"] = True
    c4.download_button(
        "💾 .md",
        data=prompt.encode("utf-8") if prompt else b"",
        file_name="system_prompt.md",
        mime="text/markdown",
        use_container_width=True,
        disabled=not prompt.strip(),
    )

    st.divider()

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
        disabled=not (description.strip() and state.model and state.endpoint),
        use_container_width=True,
    )
    if not state.model:
        c2.caption("모델을 먼저 선택하세요.")

    if enhance_clicked:
        try:
            llm = resolve(state.endpoint, model=state.model)
            with st.spinner(f"`{state.model}` 로 향상 중…"):
                enhanced = enhance_to_system_prompt(
                    llm,
                    description=description,
                    extra_constraints=constraints,
                )
            st.session_state.studio_prompt = enhanced
            st.session_state.studio_persona = None
            st.toast("✅ system prompt 생성됨 — 위 편집기에서 확인", icon="✨")
            st.rerun()
        except Exception as e:
            st.error(f"향상 실패: {type(e).__name__}: {e}")


# ============================================================
# save-as-skill dialog
# ============================================================
@st.dialog("스킬로 저장")
def save_skill_dialog():
    with st.form("save_skill_form", border=False):
        slug = st.text_input("슬러그 (id)", placeholder="예: korean-translator")
        name = st.text_input("이름", placeholder="예: 한국어 번역가")
        icon = st.text_input("아이콘", value="💬", max_chars=4)
        description = st.text_input("설명 (한 줄)")
        tags_str = st.text_input("태그 (쉼표 구분)", placeholder="예: chat, ko")
        st.caption("System prompt 는 현재 편집기 내용으로 저장됩니다.")
        cx, cy = st.columns(2)
        cancel = cx.form_submit_button("취소", use_container_width=True)
        save = cy.form_submit_button("💾 저장", type="primary", use_container_width=True)

    if cancel:
        st.session_state.pop("show_save_skill_dialog", None)
        st.rerun()
    if save:
        try:
            tags = tuple(t.strip() for t in (tags_str or "").split(",") if t.strip())
            skill = Skill(
                slug=slug.strip(),
                name=name.strip() or slug.strip(),
                icon=icon.strip() or "💬",
                kind="chat-system",
                description=description.strip(),
                system_prompt=st.session_state.studio_prompt,
                user_prompt_template="",
                tags=tags,
                default_endpoint=state.endpoint.slug if state.endpoint else None,
                default_model=state.model or None,
            )
            saved = registry.save(skill)
            st.toast(f"💾 `{saved.slug}` 저장", icon="🧰")
            st.session_state.pop("show_save_skill_dialog", None)
            st.rerun()
        except Exception as e:
            st.error(f"저장 실패: {type(e).__name__}: {e}")


if st.session_state.get("show_save_skill_dialog"):
    save_skill_dialog()


st.divider()
st.caption(
    "💡 적용 후 Chat 페이지로 이동하면 사이드바 System prompt 가 자동으로 채워집니다. "
    "Chat 의 textarea 에서 추가 편집도 가능."
)
