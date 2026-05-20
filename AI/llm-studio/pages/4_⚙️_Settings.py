import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import streamlit as st  # noqa: E402

from components import badge, inject_global_css, page_header, sidebar_brand  # noqa: E402
from shared.llm import (  # noqa: E402
    PROVIDER_KINDS,
    Endpoint,
    get_endpoints,
    has_api_key,
    list_providers,
    test_connection,
)
from shared.llm.config import (  # noqa: E402
    env_file_status,
    get_secret,
    mask_secret,
    set_secret,
    unset_secret,
)

st.set_page_config(page_title="Settings · LLM Studio", page_icon="⚙️", layout="wide")
inject_global_css()
sidebar_brand()

page_header(
    "⚙️",
    "Settings",
    "Provider · 환경변수 확인 및 편집. 변경사항은 `.env` 에 즉시 저장됩니다.",
)


# ============================================================
# 환경변수 그룹 정의
# ============================================================
# kind: "secret"  → password 입력 (값 마스킹)
#       "public"  → 일반 텍스트 (URL/HOST 등 비밀 아닌 값)
GROUPS = [
    {
        "title": "🤖 LLM Providers",
        "items": [
            ("OPENAI_API_KEY",    "secret"),
            ("OPENAI_ORG_ID",     "secret"),
            ("ANTHROPIC_API_KEY", "secret"),
            ("GOOGLE_API_KEY",    "secret"),
        ],
    },
    {
        "title": "🦙 Ollama",
        "items": [
            ("OLLAMA_BASE_URL", "public"),
        ],
    },
    {
        "title": "⚡ LiteLLM Gateway",
        "items": [
            ("LITELLM_BASE_URL", "public"),
            ("LITELLM_API_KEY",  "secret"),
        ],
    },
    {
        "title": "🖥️ 원격 실행 서버",
        "items": [
            ("REMOTE_GPU_HOST",  "public"),
            ("REMOTE_GPU_PORT",  "public"),
            ("REMOTE_GPU_TOKEN", "secret"),
            ("SPARK_MASTER_URL", "public"),
        ],
    },
    {
        "title": "🔧 앱 기본값",
        "items": [
            ("DEFAULT_PROVIDER", "public"),
            ("DEFAULT_MODEL",    "public"),
        ],
    },
]


# ============================================================
# .env 파일 상태
# ============================================================
status = env_file_status()
with st.container(border=True):
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    c1.markdown("##### `.env` 파일")
    c1.caption(status["path"])
    if status["exists"]:
        c2.metric("상태", "존재")
        c3.metric("권한", f"0{status['mode']}")
        c4.markdown(
            badge("안전", "ok") if not status["world_readable"]
            else badge("그룹/타인 읽기 가능", "warn"),
            unsafe_allow_html=True,
        )
        if status["world_readable"]:
            st.warning(
                "`.env` 파일 권한이 너무 열려있습니다. 터미널에서 `chmod 600 .env` 권장."
            )
    else:
        c2.metric("상태", "없음")
        c3.metric("권한", "—")
        c4.markdown(badge("아직 없음", "off"), unsafe_allow_html=True)
        st.info("처음 값을 저장하면 `.env` 파일이 0600 권한으로 자동 생성됩니다.")


# ============================================================
# 편집 모드 토글
# ============================================================
edit_mode = st.toggle(
    "✏️ 편집 모드",
    value=False,
    help="켜면 각 항목을 직접 수정할 수 있습니다. 변경사항은 `.env` 에 즉시 저장됩니다.",
)

if edit_mode:
    st.warning(
        "⚠️ **공개 저장소 주의** — 입력한 값은 `.env` 파일에 즉시 기록됩니다. "
        "이 저장소는 public 이지만 `.env` 는 `.gitignore` 로 차단되어 있어 커밋되지 않습니다. "
        "그래도 커밋 전 `git status` 확인 권장."
    )


# ============================================================
# 📡 연결 지점 (Endpoints)
# ============================================================
endpoints_reg = get_endpoints()

st.markdown("##### 📡 연결 지점 (Endpoints)")
st.caption(
    "이름이 붙은 LLM 연결. 같은 provider 의 여러 인스턴스를 운영할 수 있습니다. "
    "API 키는 `.env` 의 환경변수 이름으로 참조 — 실제 키 값은 아래 그룹에서 설정."
)

eps = endpoints_reg.list()
for ep in eps:
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([4, 2.5, 1.6, 2.4])
        with c1:
            badges = [badge(ep.provider_kind, "info")]
            if ep.is_default:
                badges.append(badge("기본", "off"))
            else:
                badges.append(badge("커스텀", "ok"))
            if not ep.enabled:
                badges.append(badge("비활성", "warn"))
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px'>"
                f"<span style='font-size:1.4rem'>{ep.icon}</span>"
                f"<span style='font-weight:600'>{ep.name}</span>"
                f"<code>{ep.slug}</code> {' '.join(badges)}"
                f"</div>",
                unsafe_allow_html=True,
            )
            details: list[str] = []
            if ep.base_url:
                details.append(f"`{ep.base_url}`")
            if ep.api_key_env:
                key_state = "설정됨" if has_api_key(ep) else "미설정"
                details.append(f"key env `{ep.api_key_env}` · {key_state}")
            elif ep.provider_kind == "ollama":
                details.append("key 불필요")
            if ep.default_model:
                details.append(f"기본 모델 `{ep.default_model}`")
            st.caption(" · ".join(details) or "—")
        with c2:
            if st.button(
                "🧪 테스트",
                key=f"test_ep_{ep.slug}",
                use_container_width=True,
                disabled=not ep.enabled,
            ):
                with st.spinner(f"`{ep.slug}` 테스트 중…"):
                    ok, msg = test_connection(ep)
                if ok:
                    st.toast(f"✅ {ep.slug}: {msg}", icon="📡")
                else:
                    st.toast(f"❌ {ep.slug}: {msg}", icon="⚠️")
        with c3:
            if ep.provider_kind == "ollama":
                st.page_link("pages/3_🦙_Ollama.py", label="📥 모델 관리")
        with c4:
            cx, cy = st.columns(2)
            if cx.button(
                "✏️" if not ep.is_default else "⏸️",
                key=f"edit_ep_{ep.slug}",
                use_container_width=True,
                help="편집" if not ep.is_default else ("비활성화" if ep.enabled else "활성화"),
            ):
                if ep.is_default:
                    endpoints_reg.set_enabled(ep.slug, not ep.enabled)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.session_state["edit_endpoint_slug"] = ep.slug
                    st.session_state["show_endpoint_dialog"] = True
                    st.rerun()
            if cy.button(
                "🗑️",
                key=f"del_ep_{ep.slug}",
                use_container_width=True,
                help="삭제 (기본 엔드포인트는 비활성화로 대체)",
                disabled=ep.is_default,
            ):
                try:
                    endpoints_reg.delete(ep.slug)
                    st.cache_data.clear()
                    st.toast(f"🗑️ `{ep.slug}` 삭제", icon="📡")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

cx, _ = st.columns([1.2, 4])
if cx.button("➕ 새 엔드포인트", type="primary", use_container_width=True):
    st.session_state["edit_endpoint_slug"] = None
    st.session_state["show_endpoint_dialog"] = True
    st.rerun()


# ----- dialog: create / edit endpoint -----
@st.dialog("엔드포인트 편집")
def endpoint_dialog():
    slug_to_edit = st.session_state.get("edit_endpoint_slug")
    existing = endpoints_reg.get(slug_to_edit) if slug_to_edit else None

    with st.form("endpoint_form", border=False):
        new_slug = st.text_input(
            "슬러그 (id)",
            value=existing.slug if existing else "",
            disabled=existing is not None,
            help="소문자·숫자·하이픈, 1-64자",
        )
        name = st.text_input("이름", value=existing.name if existing else "")
        kind = st.selectbox(
            "Provider kind",
            list(PROVIDER_KINDS),
            index=PROVIDER_KINDS.index(existing.provider_kind) if existing else 0,
        )
        base_url = st.text_input(
            "Base URL",
            value=existing.base_url or "" if existing else "",
            placeholder="예: http://localhost:11434 (ollama) · https://api.example.com (litellm)",
            help="ollama·litellm 에서만 사용. openai/anthropic 은 비워두세요.",
        )
        api_key_env = st.text_input(
            "API key env 변수 이름",
            value=existing.api_key_env or "" if existing else "",
            placeholder="예: OPENAI_API_KEY, ANTHROPIC_API_KEY, LITELLM_API_KEY_SEOUL",
            help="실제 값은 아래 .env 그룹 UI 로 설정하세요.",
        )
        default_model = st.text_input(
            "기본 모델 (선택)",
            value=existing.default_model or "" if existing else "",
            placeholder="예: claude-sonnet-4-6, gpt-4o-mini, llama3.1:8b",
        )
        extra_str = st.text_input(
            "추가 옵션 (key=value, 쉼표 구분)",
            value=", ".join(f"{k}={v}" for k, v in existing.extra_options.items())
                  if existing and existing.extra_options else "",
            placeholder="예: timeout=180, max_tokens=8192",
        )
        enabled = st.checkbox("활성화", value=existing.enabled if existing else True)

        c_cancel, c_save = st.columns(2)
        cancel = c_cancel.form_submit_button("취소", use_container_width=True)
        save = c_save.form_submit_button("💾 저장", type="primary", use_container_width=True)

    if cancel:
        st.session_state.pop("show_endpoint_dialog", None)
        st.rerun()

    if save:
        try:
            extra_options: dict[str, str] = {}
            for piece in (extra_str or "").split(","):
                piece = piece.strip()
                if not piece:
                    continue
                if "=" not in piece:
                    raise ValueError(f"형식 오류: '{piece}' (key=value 필요)")
                k, v = piece.split("=", 1)
                extra_options[k.strip()] = v.strip()

            ep_new = Endpoint(
                slug=new_slug.strip(),
                name=name.strip() or new_slug.strip(),
                provider_kind=kind,
                base_url=base_url.strip() or None,
                api_key_env=api_key_env.strip() or None,
                default_model=default_model.strip() or None,
                extra_options=extra_options,
                enabled=enabled,
            )
            endpoints_reg.save(ep_new)
            st.cache_data.clear()
            st.toast(f"💾 엔드포인트 `{ep_new.slug}` 저장", icon="📡")
            st.session_state.pop("show_endpoint_dialog", None)
            st.rerun()
        except Exception as e:
            st.error(f"저장 실패: {type(e).__name__}: {e}")


if st.session_state.get("show_endpoint_dialog"):
    endpoint_dialog()


# ============================================================
# 등록된 Provider (참고용)
# ============================================================
with st.container(border=True):
    st.markdown("##### 🧩 등록된 Provider 종류")
    cols = st.columns(len(list_providers()))
    for col, p in zip(cols, list_providers()):
        col.markdown(
            f"<div style='text-align:center;padding:8px 0'>"
            f"<div style='font-size:1.5rem'>📡</div>"
            f"<div style='font-weight:600;margin-top:4px'>{p}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.caption("provider 종류 자체를 추가하려면 `shared/llm/factory.register_provider()`")


# ============================================================
# 환경변수 그룹
# ============================================================
def render_group_readonly(group: dict) -> None:
    """편집 모드 OFF — 마스킹된 값 + 배지."""
    for key, kind in group["items"]:
        v = get_secret(key)
        display = v if (kind == "public" and v) else mask_secret(v)
        status_badge = badge("설정됨", "ok") if v else badge("미설정", "off")
        c1, c2, c3 = st.columns([3, 4, 1])
        c1.markdown(f"`{key}`")
        c2.write(display)
        c3.markdown(status_badge, unsafe_allow_html=True)


def render_group_edit(group: dict, form_key: str) -> None:
    """편집 모드 ON — text_input 폼 + 저장 버튼."""
    with st.form(form_key, border=False):
        new_values: dict[str, str] = {}
        for key, kind in group["items"]:
            current = get_secret(key) or ""
            if kind == "secret":
                placeholder = (
                    f"기존 값: {mask_secret(current)} (수정하려면 입력)"
                    if current else "값을 입력하세요"
                )
                new_values[key] = st.text_input(
                    key,
                    value=current,
                    type="password",
                    placeholder=placeholder,
                    help="비워두고 저장하면 `.env` 에서 제거됩니다.",
                )
            else:
                new_values[key] = st.text_input(
                    key,
                    value=current,
                    placeholder="값을 입력하세요",
                    help="비워두고 저장하면 `.env` 에서 제거됩니다.",
                )

        submitted = st.form_submit_button("💾 저장", use_container_width=True, type="primary")

    if submitted:
        added, updated, removed = 0, 0, 0
        for k, v in new_values.items():
            prev = get_secret(k) or ""
            v = (v or "").strip()
            if v == prev:
                continue
            if v == "" and prev:
                unset_secret(k)
                removed += 1
            elif v != "" and not prev:
                set_secret(k, v)
                added += 1
            else:
                set_secret(k, v)
                updated += 1

        if added or updated or removed:
            # 다른 페이지의 캐시(예: Chat 의 model 리스트) 도 초기화
            st.cache_data.clear()
            parts = []
            if added:   parts.append(f"추가 {added}")
            if updated: parts.append(f"수정 {updated}")
            if removed: parts.append(f"제거 {removed}")
            st.toast(f"✅ {' · '.join(parts)} — .env 반영됨", icon="⚙️")
            st.rerun()
        else:
            st.toast("변경사항 없음")


for group in GROUPS:
    with st.container(border=True):
        st.markdown(f"##### {group['title']}")
        if edit_mode:
            render_group_edit(group, form_key=f"form_{group['title']}")
        else:
            render_group_readonly(group)


# ============================================================
# 안내
# ============================================================
st.markdown("---")
with st.container(border=True):
    st.markdown("##### 🔐 보안 메모")
    st.markdown(
        """
        - 모든 값은 `.env` 파일에 저장되며 이 파일은 `.gitignore` 처리되어 **커밋되지 않습니다**.
        - 새 비밀 키가 필요하면:
            1. `.env.example` 에 **키 이름만** (값 없이) 추가
            2. 위 그룹 정의에 항목 추가 (`shared/llm/factory.GROUPS`)
            3. 코드에서는 `from shared.llm.config import get_secret` 으로만 사용 — 하드코딩 금지
        - 실수로 `.env` 또는 키를 커밋했다면 **즉시 해당 키를 발급처에서 무효화** 후 git history 정리.
        """
    )
