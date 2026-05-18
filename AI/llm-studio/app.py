import _bootstrap  # noqa: F401  -- adds project root to sys.path

import streamlit as st

from components import (
    badge,
    inject_global_css,
    page_header,
    sidebar_brand,
)
from shared.llm import get_provider
from shared.llm.config import get_secret

st.set_page_config(
    page_title="LLM Studio",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()
sidebar_brand()

page_header(
    icon="🧪",
    title="LLM Studio",
    subtitle="Streamlit 기반 LLM 플레이그라운드 · 여러 provider 를 한 곳에서.",
)


# ============================================================
# Provider 상태 (실시간 점검)
# ============================================================
@st.cache_data(ttl=15, show_spinner=False)
def check_status() -> list[dict]:
    """Light health-check each provider — returns rows for the dashboard."""
    rows: list[dict] = []

    # ---- Ollama ----
    try:
        o = get_provider("ollama", model="-")
        if o.health():
            n = len(o.list_models())
            rows.append({"name": "Ollama", "icon": "🦙", "status": "ok",
                         "detail": f"{n}개 모델 설치됨", "tip": o.base_url})
        else:
            rows.append({"name": "Ollama", "icon": "🦙", "status": "err",
                         "detail": "서버 연결 불가", "tip": o.base_url})
    except Exception as e:
        rows.append({"name": "Ollama", "icon": "🦙", "status": "err",
                     "detail": f"오류: {e}", "tip": "-"})

    # ---- OpenAI / Anthropic / LiteLLM — key 존재 + 패키지 import 가능 여부 ----
    for label, icon, name, env_key in [
        ("OpenAI",    "☁️", "openai",    "OPENAI_API_KEY"),
        ("Anthropic", "🧠", "anthropic", "ANTHROPIC_API_KEY"),
        ("LiteLLM",   "⚡", "litellm",   "LITELLM_API_KEY"),
    ]:
        has_key = bool(get_secret(env_key)) or (name == "litellm" and bool(get_secret("LITELLM_BASE_URL")))
        try:
            get_provider(name, model="-")
            rows.append({"name": label, "icon": icon, "status": "ok",
                         "detail": "준비 완료", "tip": "키 설정됨"})
        except ImportError:
            rows.append({"name": label, "icon": icon, "status": "off",
                         "detail": "패키지 미설치", "tip": f"pip install 'ai-tools[{name}]'"})
        except RuntimeError:
            rows.append({"name": label, "icon": icon, "status": "warn",
                         "detail": f"{env_key} 없음" if not has_key else "키 오류",
                         "tip": ".env 에 추가"})
        except Exception as e:
            rows.append({"name": label, "icon": icon, "status": "err",
                         "detail": str(e)[:40], "tip": "-"})

    return rows


st.markdown("##### 시스템 상태")
c1, c2, c3, c4 = st.columns(4)
rows = check_status()
for col, row in zip([c1, c2, c3, c4], rows):
    with col:
        with st.container(border=True):
            label_map = {"ok": "정상", "warn": "주의", "err": "오프", "off": "비활성"}
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                f"<span style='font-size:1.3rem'>{row['icon']} <b>{row['name']}</b></span>"
                f"{badge(label_map[row['status']], row['status'])}"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(row["detail"])
            st.caption(f"`{row['tip']}`")

st.write("")  # spacing


# ============================================================
# 빠른 시작 — 페이지 카드
# ============================================================
st.markdown("##### 빠른 시작")

cards = [
    {"icon": "💬", "title": "Chat",     "page": "pages/1_💬_Chat.py",
     "desc": "Provider · 모델 선택 후 대화, `.md` 익스포트"},
    {"icon": "📁", "title": "Files",    "page": "pages/2_📁_Files.py",
     "desc": "파일 업로드 · 리스트 · 다운로드 · 삭제"},
    {"icon": "🦙", "title": "Ollama",   "page": "pages/3_🦙_Ollama.py",
     "desc": "인기 모델 원클릭 Pull · 설치 모델 관리"},
    {"icon": "⚙️", "title": "Settings", "page": "pages/4_⚙️_Settings.py",
     "desc": "Provider · 환경변수 상태 확인 (마스킹)"},
]
cols = st.columns(4)
for col, card in zip(cols, cards):
    with col:
        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:2rem;line-height:1'>{card['icon']}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**{card['title']}**")
            st.caption(card["desc"])
            st.page_link(card["page"], label="열기 →", icon=None)

st.write("")
st.caption(
    "🔐 보안 — 모든 비밀 값은 `.env` 에서 로드, 화면 표시는 마스킹됩니다. · 시스템 상태는 15초 캐시."
)
