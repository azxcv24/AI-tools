"""Shared sidebar widget — endpoint + model + skill + system prompt.

Each page calls render_sidebar(page_id, kinds=[...], with_task=False,
with_limits=False) and gets a SidebarState dataclass back. Pages then read
state.endpoint, state.model, state.skill, state.system_prompt, state.task,
state.timeout_seconds, state.memory_mb.

Sidebar layout (top → bottom):
  1. 🔌 Endpoint selectbox
  2. Model dropdown (cached, per-endpoint)
  3. 🧰 Skill selectbox (filtered by `kinds`)
  4. 📝 System prompt textarea (pre-filled by selected skill)
  5. (optional) 🛠 Task textarea (with_task=True)
  6. (optional) Timeout + memory sliders (with_limits=True)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import streamlit as st

from shared.llm import (
    Endpoint,
    get_endpoints,
    resolve,
)
from shared.skills import Skill, SkillKind, get_registry

from .ui import badge


@dataclass
class SidebarState:
    endpoint: Endpoint | None
    model: str
    skill: Skill | None
    system_prompt: str
    task: str
    timeout_seconds: int | None = None
    memory_mb: int | None = None


# ---------- model fetch cache ----------

@st.cache_data(ttl=300, show_spinner="모델 리스트 조회 중…")
def _fetch_models(endpoint_slug: str) -> tuple[list[str], str | None]:
    ep = get_endpoints().get(endpoint_slug)
    if ep is None:
        return [], f"엔드포인트를 찾을 수 없음: {endpoint_slug}"
    try:
        provider = resolve(ep, model="-")
        return list(provider.list_models()), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def clear_model_cache() -> None:
    _fetch_models.clear()


# ---------- helpers ----------

def _endpoints_for_picker() -> list[Endpoint]:
    return [e for e in get_endpoints().list() if e.enabled]


def _apply_skill_to_state(page_id: str, skill: Skill | None) -> None:
    """When a skill is selected, fill the system prompt + task slots."""
    sys_key = f"sidebar_system__{page_id}"
    task_key = f"sidebar_task__{page_id}"
    applied_key = f"sidebar_skill__{page_id}"

    prev_slug = st.session_state.get(applied_key)
    new_slug = skill.slug if skill else None
    if prev_slug == new_slug:
        return  # no change

    if skill:
        st.session_state[sys_key] = skill.system_prompt
        # Only overwrite task if template carries a default (not {task} placeholder)
        if "{task}" not in skill.user_prompt_template:
            st.session_state[task_key] = skill.user_prompt_template
        else:
            st.session_state.setdefault(task_key, "")
    else:
        # When clearing a skill, leave system/task as-is so user edits aren't lost.
        pass

    st.session_state[applied_key] = new_slug


# ---------- main entry point ----------

def render_sidebar(
    page_id: str,
    *,
    kinds: Sequence[SkillKind] | None = None,
    with_task: bool = False,
    with_limits: bool = False,
    default_system_prompt: str = "You are a helpful assistant.",
) -> SidebarState:
    """Render the shared sidebar and return the resolved selection."""
    endpoints = _endpoints_for_picker()
    if not endpoints:
        with st.sidebar:
            st.error("활성화된 엔드포인트가 없습니다. Settings → 📡 연결 지점에서 추가하세요.")
        return SidebarState(endpoint=None, model="", skill=None, system_prompt="", task="")

    with st.sidebar:
        # ----- 🔌 Endpoint -----
        st.markdown("##### 🔌 엔드포인트")
        ep_key = f"sidebar_endpoint__{page_id}"
        prev_slug = st.session_state.get(ep_key)
        ep_slugs = [e.slug for e in endpoints]
        ep_idx = ep_slugs.index(prev_slug) if prev_slug in ep_slugs else 0
        chosen_slug = st.selectbox(
            "Endpoint",
            ep_slugs,
            index=ep_idx,
            format_func=lambda s: f"{next((e for e in endpoints if e.slug == s)).icon}  "
                                  f"{next((e for e in endpoints if e.slug == s)).name}",
            key=f"sidebar_endpoint_sel__{page_id}",
            label_visibility="collapsed",
        )
        st.session_state[ep_key] = chosen_slug
        endpoint = next(e for e in endpoints if e.slug == chosen_slug)

        # If endpoint changed, drop the cached model so a new one is chosen.
        last_ep_key = f"sidebar_last_ep__{page_id}"
        if st.session_state.get(last_ep_key) and st.session_state[last_ep_key] != chosen_slug:
            st.session_state.pop(f"sidebar_model__{page_id}", None)
        st.session_state[last_ep_key] = chosen_slug

        # ----- Model -----
        c1, c2 = st.columns([4, 1])
        c1.caption("Model")
        if c2.button("🔄", help="모델 리스트 새로고침", use_container_width=True,
                     key=f"sidebar_refresh__{page_id}"):
            clear_model_cache()
            st.rerun()

        models, err = _fetch_models(endpoint.slug)
        model_key = f"sidebar_model__{page_id}"
        if err:
            st.warning(f"리스트 조회 실패\n\n```\n{err}\n```")
            model = st.text_input(
                "Model (수동)",
                value=st.session_state.get(model_key, endpoint.default_model or ""),
                key=f"sidebar_model_input__{page_id}",
                label_visibility="collapsed",
            )
        elif not models:
            st.info("모델 없음 — 직접 입력")
            model = st.text_input(
                "Model (수동)",
                value=st.session_state.get(model_key, endpoint.default_model or ""),
                key=f"sidebar_model_input__{page_id}",
                label_visibility="collapsed",
            )
        else:
            prev_model = st.session_state.get(model_key) or endpoint.default_model
            idx = models.index(prev_model) if prev_model in models else 0
            model = st.selectbox(
                "Model",
                models,
                index=idx,
                key=f"sidebar_model_sel__{page_id}",
                label_visibility="collapsed",
            )
        st.session_state[model_key] = model

        # ----- 🧰 Skill -----
        st.divider()
        st.markdown("##### 🧰 스킬")
        skill_kinds = list(kinds) if kinds else None
        registry = get_registry()
        skills = registry.by_kind(*skill_kinds) if skill_kinds else registry.list()

        skill_slug_key = f"sidebar_skill__{page_id}"
        prev_skill_slug = st.session_state.get(skill_slug_key)
        skill_slugs = ["(없음)"] + [s.slug for s in skills]
        skill_idx = skill_slugs.index(prev_skill_slug) if prev_skill_slug in skill_slugs else 0

        def _fmt_skill(slug: str) -> str:
            if slug == "(없음)":
                return "(없음)"
            sk = next((x for x in skills if x.slug == slug), None)
            if sk is None:
                return slug
            tail = " 🔒" if sk.readonly else ""
            return f"{sk.icon} {sk.name}{tail}"

        chosen_skill_slug = st.selectbox(
            "Skill",
            skill_slugs,
            index=skill_idx,
            format_func=_fmt_skill,
            key=f"sidebar_skill_sel__{page_id}",
            label_visibility="collapsed",
        )
        chosen_skill: Skill | None = (
            None if chosen_skill_slug == "(없음)"
            else next((x for x in skills if x.slug == chosen_skill_slug), None)
        )
        _apply_skill_to_state(page_id, chosen_skill)

        if chosen_skill:
            st.markdown(
                badge(f"{chosen_skill.icon} {chosen_skill.name}", "info"),
                unsafe_allow_html=True,
            )
            st.caption(chosen_skill.description)

        # ----- 📝 System prompt -----
        st.divider()
        st.markdown("##### 📝 시스템 프롬프트")

        # Compatibility with the old Prompt-Studio handoff
        sys_key = f"sidebar_system__{page_id}"
        if (
            page_id in ("chat", "prompt-studio")
            and "applied_system_prompt" in st.session_state
            and sys_key not in st.session_state
        ):
            st.session_state[sys_key] = st.session_state.pop("applied_system_prompt")
            applied_label = st.session_state.pop("applied_persona_label", None)
            if applied_label:
                st.markdown(badge(f"✨ {applied_label}", "info"), unsafe_allow_html=True)
            else:
                st.markdown(badge("✨ Prompt Studio 에서 적용됨", "info"), unsafe_allow_html=True)

        initial_sys = st.session_state.get(sys_key, default_system_prompt)
        system_prompt = st.text_area(
            "System prompt",
            value=initial_sys,
            height=140,
            key=f"sidebar_system_input__{page_id}",
            label_visibility="collapsed",
        )
        st.session_state[sys_key] = system_prompt

        # ----- 🛠 Task (Excel only) -----
        task = ""
        if with_task:
            st.markdown("##### 🛠 작업 설명")
            task_key = f"sidebar_task__{page_id}"
            initial_task = st.session_state.get(task_key, "")
            task = st.text_area(
                "Task",
                value=initial_task,
                height=110,
                placeholder="예: 비목별로 묶어 모든 연차의 예산을 합산하라.",
                key=f"sidebar_task_input__{page_id}",
                label_visibility="collapsed",
            )
            st.session_state[task_key] = task

        # ----- 🔒 Limits (Excel only) -----
        timeout_seconds: int | None = None
        memory_mb: int | None = None
        if with_limits:
            st.divider()
            st.markdown("##### 🔒 실행 제한")
            timeout_seconds = st.slider(
                "타임아웃 (초)", 5, 300, 60, step=5,
                key=f"sidebar_timeout__{page_id}",
            )
            memory_mb = st.slider(
                "메모리 (MB)", 128, 4096, 1024, step=128,
                key=f"sidebar_memory__{page_id}",
            )
            st.caption("LLM 생성 코드는 격리 subprocess 에서 실행됩니다.")

    return SidebarState(
        endpoint=endpoint,
        model=model or "",
        skill=chosen_skill,
        system_prompt=system_prompt,
        task=task,
        timeout_seconds=timeout_seconds,
        memory_mb=memory_mb,
    )
