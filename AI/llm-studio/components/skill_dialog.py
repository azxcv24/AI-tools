"""Shared "save as skill" dialog — used by Chat and Prompt Studio.

Both pages previously carried their own near-identical dialog. This unifies
them: the caller passes the prompt content + which kinds are selectable, and
the dialog handles the form, validation, and persistence to the registry.

Open it the same way Streamlit dialogs are opened elsewhere — set a session
flag, then call this at the bottom of the script:

    if st.session_state.get("show_save_dialog"):
        save_skill_dialog(flag_key="show_save_dialog", system_prompt=..., ...)
"""
from __future__ import annotations

from typing import Sequence

import streamlit as st

from shared.skills import Skill, get_registry


def _default_icon(kind: str) -> str:
    return "📊" if kind == "excel-pandas" else "💬"


@st.dialog("스킬로 저장")
def save_skill_dialog(
    *,
    flag_key: str,
    system_prompt: str,
    user_template: str | None = None,
    kind_choices: Sequence[str] = ("chat-system",),
    suggested_kind: str = "chat-system",
    default_endpoint: str | None = None,
    default_model: str | None = None,
    intro: str | None = None,
) -> None:
    """Render the save-as-skill dialog.

    - `system_prompt`     pre-fills the (editable) system-prompt field.
    - `user_template`     None → hide the field and save an empty template;
                          otherwise pre-fills an editable user-template field.
    - `kind_choices`      one entry → fixed (no selector); many → a selectbox.
    - `flag_key`          session_state flag to clear when the dialog closes.
    """
    kind_choices = tuple(kind_choices) or ("chat-system",)
    if intro:
        st.caption(intro)

    with st.form("save_skill_form", border=False):
        slug = st.text_input(
            "슬러그 (id)", placeholder="예: my-monthly-summary",
            help="소문자·숫자·하이픈, 1-64자",
        )
        name = st.text_input("이름", placeholder="예: 월별 매출 요약")

        c_icon, c_kind = st.columns([1, 3])
        icon = c_icon.text_input("아이콘", value=_default_icon(suggested_kind), max_chars=4)
        if len(kind_choices) > 1:
            kind = c_kind.selectbox(
                "Kind",
                list(kind_choices),
                index=(
                    kind_choices.index(suggested_kind)
                    if suggested_kind in kind_choices else 0
                ),
                help="excel-pandas: Excel 작업용 / chat-system: 일반 대화용",
            )
        else:
            kind = kind_choices[0]
            c_kind.text_input("Kind", value=kind, disabled=True)

        description = st.text_input("설명 (한 줄)")
        tags_str = st.text_input("태그 (쉼표 구분)", placeholder="예: excel, budget, ko")

        st.markdown("**System prompt**")
        sys_prompt = st.text_area(
            "system", value=system_prompt, height=140, label_visibility="collapsed",
        )

        user_tmpl = ""
        if user_template is not None:
            st.markdown("**User prompt template** — `{file_list}` 등 자리표시자 사용 권장")
            user_tmpl = st.text_area(
                "user_template", value=user_template, height=140,
                label_visibility="collapsed",
            )

        cx, cy = st.columns(2)
        cancel = cx.form_submit_button("취소", use_container_width=True)
        save = cy.form_submit_button("💾 저장", type="primary", use_container_width=True)

    if cancel:
        st.session_state.pop(flag_key, None)
        st.rerun()

    if save:
        try:
            tags = tuple(t.strip() for t in (tags_str or "").split(",") if t.strip())
            new = Skill(
                slug=slug.strip(),
                name=name.strip() or slug.strip(),
                icon=icon.strip() or _default_icon(kind),
                kind=kind,
                description=description.strip(),
                system_prompt=sys_prompt,
                user_prompt_template=user_tmpl,
                tags=tags,
                default_endpoint=default_endpoint,
                default_model=default_model,
            )
            saved = get_registry().save(new)
            st.toast(
                f"💾 `{saved.slug}` 저장 — 사이드바 🧰 스킬에서 즉시 사용 가능",
                icon="🧰",
            )
            st.session_state.pop(flag_key, None)
            st.rerun()
        except Exception as e:
            st.error(f"저장 실패: {type(e).__name__}: {e}")
