import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import streamlit as st  # noqa: E402

from components import (  # noqa: E402
    badge,
    empty_state,
    inject_global_css,
    page_header,
    sidebar_brand,
)
from shared.llm import get_endpoints  # noqa: E402
from shared.skills import (  # noqa: E402
    SKILL_KINDS,
    ReadOnlySkillError,
    Skill,
    SkillKind,
    get_registry,
    render_template,
)

st.set_page_config(page_title="Skills · LLM Studio", page_icon="🧰", layout="wide")
inject_global_css()
sidebar_brand()

page_header(
    "🧰",
    "Skills",
    "재사용 가능한 시스템 프롬프트·작업 템플릿. 사이드바 드롭다운으로 어디서나 적용.",
)

KIND_LABELS: dict[SkillKind, tuple[str, str]] = {
    "chat-system": ("💬 Chat", "Chat 사이드바 시스템 프롬프트"),
    "excel-pandas": ("📊 Excel", "Excel Agent 의 pandas 코드 생성"),
    "excel-structure": ("🔍 Structure", "Excel 구조 자동 분석 (내부 사용)"),
    "prompt-enhance": ("✨ Enhance", "Prompt Studio 의 향상 메타 프롬프트"),
}


# ============================================================
# state
# ============================================================
if "skill_page_mode" not in st.session_state:
    st.session_state.skill_page_mode = "list"   # "list" | "edit" | "new"
if "skill_page_slug" not in st.session_state:
    st.session_state.skill_page_slug = None
if "skill_kind_filter" not in st.session_state:
    st.session_state.skill_kind_filter = "all"

registry = get_registry()


# ============================================================
# list mode
# ============================================================
def render_list() -> None:
    all_skills = registry.list()

    # ----- header row: filters + new -----
    cf, ck, cs, cn = st.columns([1.2, 4, 4, 1.5])
    with cf:
        st.markdown(f"##### 전체 ({len(all_skills)})")
    with ck:
        opts = ["all"] + list(SKILL_KINDS)
        st.session_state.skill_kind_filter = st.radio(
            "Kind 필터",
            opts,
            index=opts.index(st.session_state.skill_kind_filter),
            horizontal=True,
            format_func=lambda k: "전체" if k == "all" else KIND_LABELS[k][0],
            label_visibility="collapsed",
            key="skill_kind_radio",
        )
    with cs:
        query = st.text_input(
            "검색", placeholder="🔎 이름 · 설명 · 태그",
            label_visibility="collapsed", key="skill_search_q",
        )
    with cn:
        if st.button("➕ 새 스킬", type="primary", use_container_width=True):
            st.session_state.skill_page_mode = "new"
            st.session_state.skill_page_slug = None
            st.rerun()

    # ----- filter -----
    kind_filter = st.session_state.skill_kind_filter
    q = (query or "").strip().lower()
    visible: list[Skill] = []
    for s in all_skills:
        if kind_filter != "all" and s.kind != kind_filter:
            continue
        if q:
            hay = " ".join([s.name, s.description, " ".join(s.tags)]).lower()
            if q not in hay:
                continue
        visible.append(s)

    if not visible:
        empty_state(
            icon="🧰",
            title="조건에 맞는 스킬이 없습니다",
            hint="필터·검색을 비우거나 ➕ 새 스킬 로 직접 만들어 보세요.",
        )
        return

    # ----- cards -----
    for s in visible:
        kind_label, kind_desc = KIND_LABELS.get(s.kind, (s.kind, ""))
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([0.6, 4.5, 1.6, 1.4, 1.4])
            c1.markdown(f"<div style='font-size:1.6rem'>{s.icon}</div>", unsafe_allow_html=True)
            with c2:
                lock = " 🔒" if s.readonly else ""
                st.markdown(f"**{s.name}**{lock}")
                st.caption(s.description)
                tag_html = " ".join(badge(t, "off") for t in s.tags) if s.tags else ""
                if tag_html:
                    st.markdown(tag_html, unsafe_allow_html=True)
            c3.markdown(badge(kind_label, "info"), unsafe_allow_html=True)
            c3.caption(kind_desc)
            # actions
            if c4.button("✏️ 보기" if s.readonly else "✏️ 편집",
                         key=f"edit_{s.slug}", use_container_width=True):
                st.session_state.skill_page_mode = "edit"
                st.session_state.skill_page_slug = s.slug
                st.rerun()
            if s.readonly:
                if c5.button("📋 복제", key=f"clone_{s.slug}", use_container_width=True):
                    try:
                        new = registry.clone(s.slug, f"{s.slug}-copy")
                        st.session_state.skill_page_mode = "edit"
                        st.session_state.skill_page_slug = new.slug
                        st.toast(f"✅ `{new.slug}` 로 복제", icon="📋")
                        st.rerun()
                    except Exception as e:
                        st.error(f"복제 실패: {e}")
            else:
                if c5.button("🗑️ 삭제", key=f"del_{s.slug}", use_container_width=True):
                    try:
                        registry.delete(s.slug)
                        st.toast(f"🗑️ `{s.slug}` 삭제", icon="🧰")
                        st.rerun()
                    except ReadOnlySkillError as e:
                        st.error(str(e))


# ============================================================
# edit / new mode
# ============================================================
def render_form(*, mode: str) -> None:
    slug = st.session_state.skill_page_slug
    existing: Skill | None = registry.get(slug) if slug else None
    readonly = bool(existing and existing.readonly)

    title = "🔍 시드 스킬 보기" if readonly else ("✏️ 스킬 편집" if mode == "edit" else "➕ 새 스킬")
    st.markdown(f"#### {title}")
    if readonly:
        st.info("🔒 시드 스킬은 수정할 수 없습니다. 변경하려면 `📋 복제` 후 사본을 편집하세요.")

    # ----- form -----
    endpoint_list = get_endpoints().list()
    endpoint_slugs = ["(없음)"] + [e.slug for e in endpoint_list]

    with st.form(f"skill_form_{mode}", clear_on_submit=False, border=False):
        left, right = st.columns([1.2, 2])

        # ---- left: metadata ----
        with left:
            new_slug = st.text_input(
                "슬러그 (id)",
                value=existing.slug if existing else "",
                disabled=(mode == "edit" or readonly),
                help="소문자·숫자·하이픈, 1-64자. 저장 후 변경 불가.",
            )
            name = st.text_input(
                "이름", value=existing.name if existing else "",
                disabled=readonly,
            )
            icon = st.text_input(
                "아이콘 (이모지 1자)",
                value=existing.icon if existing else "🧩",
                disabled=readonly, max_chars=4,
            )
            kind_options = list(SKILL_KINDS)
            kind = st.selectbox(
                "Kind",
                kind_options,
                index=kind_options.index(existing.kind) if existing else 0,
                format_func=lambda k: f"{KIND_LABELS[k][0]}  ·  {KIND_LABELS[k][1]}",
                disabled=readonly,
            )
            description = st.text_input(
                "설명 (한 줄)",
                value=existing.description if existing else "",
                disabled=readonly,
            )
            tags_str = st.text_input(
                "태그 (쉼표 구분)",
                value=", ".join(existing.tags) if existing else "",
                placeholder="예: excel, ko, 예실",
                disabled=readonly,
            )
            default_ep = st.selectbox(
                "기본 엔드포인트",
                endpoint_slugs,
                index=(
                    endpoint_slugs.index(existing.default_endpoint)
                    if existing and existing.default_endpoint in endpoint_slugs
                    else 0
                ),
                disabled=readonly,
            )
            default_model = st.text_input(
                "기본 모델", value=existing.default_model or "" if existing else "",
                disabled=readonly,
            )
            sample_files_str = st.text_input(
                "샘플 파일 (쉼표 구분)",
                value=", ".join(existing.sample_files) if existing else "",
                disabled=readonly,
            )

        # ---- right: prompts ----
        with right:
            system_prompt = st.text_area(
                "System prompt",
                value=existing.system_prompt if existing else "",
                height=240,
                disabled=readonly,
            )
            user_prompt_template = st.text_area(
                "User prompt template",
                value=existing.user_prompt_template if existing else "",
                height=180,
                help="자리표시자: {task}, {file_list}, {schema_json}, {file_name}, {raw_preview}, {column_candidates}",
                disabled=readonly,
            )
            with st.expander("🔄 미리보기 (자리표시자 치환)"):
                preview = render_template(
                    user_prompt_template,
                    task="<사용자 작업 설명>",
                    file_list="a.xlsx, b.xlsx",
                    schema_json='{"key_columns": ["비목 번호"], ...}',
                    file_name="sample.xlsx",
                    raw_preview="(raw 15 lines)",
                    column_candidates='{"header=0": [...], "header=[0,1]": [...]}',
                )
                st.code(preview or "(템플릿 비어있음)", language="markdown")

        # ---- footer ----
        st.divider()
        cancel_col, save_col = st.columns([1, 1])
        cancel = cancel_col.form_submit_button(
            "취소", use_container_width=True,
        )
        save = save_col.form_submit_button(
            "💾 저장", type="primary", use_container_width=True, disabled=readonly,
        )

    if cancel:
        st.session_state.skill_page_mode = "list"
        st.session_state.skill_page_slug = None
        st.rerun()

    if save and not readonly:
        try:
            tags = tuple(t.strip() for t in (tags_str or "").split(",") if t.strip())
            sample_files = tuple(
                t.strip() for t in (sample_files_str or "").split(",") if t.strip()
            )
            ep = default_ep if default_ep and default_ep != "(없음)" else None
            new_skill = Skill(
                slug=new_slug.strip(),
                name=name.strip() or new_slug.strip(),
                icon=icon.strip() or "🧩",
                kind=kind,
                description=description.strip(),
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template,
                tags=tags,
                default_endpoint=ep,
                default_model=default_model.strip() or None,
                sample_files=sample_files,
                readonly=False,
            )
            saved = registry.save(new_skill)
            st.toast(f"💾 `{saved.slug}` 저장 (v{saved.version})", icon="🧰")
            st.session_state.skill_page_mode = "list"
            st.session_state.skill_page_slug = None
            st.rerun()
        except Exception as e:
            st.error(f"저장 실패: {type(e).__name__}: {e}")


# ============================================================
# dispatch
# ============================================================
mode = st.session_state.skill_page_mode
if mode == "list":
    render_list()
else:
    if st.button("← 목록으로", key="back_to_list"):
        st.session_state.skill_page_mode = "list"
        st.session_state.skill_page_slug = None
        st.rerun()
    render_form(mode=mode)
