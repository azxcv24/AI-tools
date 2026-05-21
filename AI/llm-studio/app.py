import _bootstrap  # noqa: F401  -- adds project root to sys.path

import streamlit as st

from components import (
    badge,
    inject_global_css,
    page_header,
    sidebar_brand,
)
from shared.llm import get_endpoints, has_api_key, test_connection

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
    subtitle="Streamlit 기반 LLM 플레이그라운드 · 엔드포인트·스킬·격리 실행을 한 곳에서.",
)


# ============================================================
# 엔드포인트 상태 (실시간 점검)
# ============================================================
@st.cache_data(ttl=15, show_spinner=False)
def _endpoint_status_rows() -> list[dict]:
    rows: list[dict] = []
    for ep in get_endpoints().list():
        if not ep.enabled:
            rows.append({
                "icon": ep.icon, "name": ep.name, "status": "off",
                "detail": "비활성", "tip": ep.slug,
            })
            continue
        if ep.api_key_env and not has_api_key(ep):
            rows.append({
                "icon": ep.icon, "name": ep.name, "status": "warn",
                "detail": f"{ep.api_key_env} 없음", "tip": "Settings 에서 설정",
            })
            continue
        ok, msg = test_connection(ep)
        rows.append({
            "icon": ep.icon, "name": ep.name,
            "status": "ok" if ok else "err",
            "detail": msg[:50],
            "tip": ep.slug,
        })
    return rows


st.markdown("##### 📡 엔드포인트 상태")
rows = _endpoint_status_rows()[:4]   # show first 4 to fit the row
if not rows:
    st.info("등록된 엔드포인트가 없습니다. Settings 페이지에서 추가하세요.")
else:
    cols = st.columns(len(rows))
    label_map = {"ok": "정상", "warn": "주의", "err": "오류", "off": "비활성"}
    for col, row in zip(cols, rows):
        with col:
            with st.container(border=True):
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                    f"<span style='font-size:1.3rem'>{row['icon']} <b>{row['name']}</b></span>"
                    f"{badge(label_map[row['status']], row['status'])}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.caption(row["detail"])
                st.caption(f"`{row['tip']}`")

st.write("")


# ============================================================
# 빠른 시작
# ============================================================
st.markdown("##### 빠른 시작")

cards = [
    {"icon": "💬", "title": "Chat",          "page": "pages/1_💬_Chat.py",
     "desc": "파일 드롭 + 자동 엑셀 분석 + 코드 자동 실행 (Code Interpreter 스타일)"},
    {"icon": "✨", "title": "Prompt Studio", "page": "pages/2_✨_Prompt_Studio.py",
     "desc": "페르소나 라이브러리 + 한 줄 → system prompt 향상"},
    {"icon": "🧰", "title": "Skills",        "page": "pages/3_🧰_Skills.py",
     "desc": "재사용 가능한 시스템 프롬프트·작업 템플릿 관리"},
    {"icon": "🦙", "title": "Ollama",        "page": "pages/4_🦙_Ollama.py",
     "desc": "인기 모델 원클릭 Pull · 설치 관리"},
    {"icon": "⚙️", "title": "Settings",      "page": "pages/5_⚙️_Settings.py",
     "desc": "📡 엔드포인트 + 환경변수 편집"},
]
PER_ROW = 3
for row_start in range(0, len(cards), PER_ROW):
    row_cards = cards[row_start : row_start + PER_ROW]
    cols = st.columns(PER_ROW)
    for col, card in zip(cols, row_cards):
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
    "🔐 비밀 값은 `.env` 에서 로드, 표시는 마스킹. · 엔드포인트 상태는 15초 캐시."
)
