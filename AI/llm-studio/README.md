# LLM Studio

Streamlit 기반 LLM 플레이그라운드. AI 카테고리의 첫 번째 도구.

## 실행

```bash
# 1) 의존성 설치 (프로젝트 루트에서)
pip install -e .
pip install -e '.[openai]'      # OpenAI
pip install -e '.[anthropic]'   # Anthropic
pip install -e '.[litellm]'     # LiteLLM 게이트웨이 (SDK 모드 — proxy 모드는 불필요)
pip install -e '.[all]'         # 전부

# 2) 환경변수 설정
cp .env.example .env            # 루트의 .env 를 채움 (gitignored)

# 3) Streamlit 실행
cd AI/llm-studio
streamlit run app.py
```

브라우저에서 [http://localhost:8501](http://localhost:8501) 열림.

## 페이지

| 페이지 | 기능 |
|---|---|
| 💬 Chat (1)            | ChatGPT-style 통합 UI — 사이드바: 엔드포인트·모델·🧰 스킬·시스템 프롬프트 (재사용 프롬프트는 🧰 Skills 로 저장). 본문: 채팅 입력 + 📎 인라인 파일 첨부 → 엑셀/CSV 자동 schema 주입 → **`excel-default` 스킬 자동 선택** → LLM 이 ```python``` 응답하면 **격리 sandbox 에서 자동 실행** → 다단 헤더·그룹 소계·합계 양식 보존된 결과 파일을 다운로드·미리보기 카드로 |
| ✨ Prompt Studio (2)   | 라이브러리(=chat-system 스킬) + 한 줄 → system prompt 향상 + 💾 스킬로 저장 |
| 🧰 Skills (3)          | 시드 14개 (🤖 excel-default + Excel 4 + 페르소나 8 + enhance 1) + 사용자 스킬 CRUD (kind 필터, 검색, 복제) |
| 🦙 Ollama (4)          | 모델 pull(진행률) · 설치 리스트 · 삭제 · `?endpoint=<slug>` 로 다중 서버 |
| ⚙️ Settings (5)        | **📡 연결 지점 (Endpoints)** + .env 편집(편집 모드 토글, 0600) |

업로드 파일·사용자 스킬·endpoints.json 은 모두 `AI/llm-studio/data/` 에 저장 (전 경로 gitignored).
이전 페이지였던 **Files / Excel Agent** 는 Chat 한 곳으로 통합됐습니다 — 파일은 채팅 입력에서 직접 드롭하고, 엑셀 작업은 첨부 + 자연어 요청으로 자동 처리됩니다.

## 구조

```
llm-studio/
├── app.py                    · 랜딩 + 엔드포인트 상태
├── _bootstrap.py             · sys.path + data dir + SkillRegistry/EndpointRegistry 와이어업
├── components/
│   ├── ui.py                 · header · badge · empty_state · section · sidebar_brand · fmt_bytes
│   ├── sidebar.py            · render_sidebar(page_id, kinds, with_task, with_limits, with_system_prompt, default_skill_slug)
│   ├── skill_dialog.py       · save_skill_dialog(...) — Chat·Prompt Studio 공용 "스킬로 저장"
│   └── ollama_ui.py          · POPULAR_CHAT/EMBED 카탈로그 + run_pull() — Ollama·Settings 공용
├── pages/
│   ├── 1_💬_Chat.py          · ChatGPT-style 통합 (파일 드롭 + Code Interpreter)
│   ├── 2_✨_Prompt_Studio.py
│   ├── 3_🧰_Skills.py
│   ├── 4_🦙_Ollama.py
│   └── 5_⚙️_Settings.py
└── data/                     · uploads · outputs · skills · endpoints.json (gitignored)
```

## 사이드바 공유 컴포넌트

거의 모든 페이지가 동일한 사이드바 골격을 쓰도록 [`components/sidebar.py`](components/sidebar.py) 가 통합. 호출 1줄로 대체:

```python
from components import render_sidebar

state = render_sidebar(
    "chat",
    kinds=["chat-system", "excel-pandas"],  # 사이드바 스킬 드롭다운에 보일 kind
    default_skill_slug="excel-default" if has_tabular else None,  # 엑셀 첨부 시 자동 기본 선택
)

# state.endpoint, state.model, state.skill, state.system_prompt
```

**자동 기본 선택**: `default_skill_slug` 가 주어지고 사용자가 아직 명시적으로 다른 선택을 한 적이 없으면 (None/"(없음)") 그 스킬을 promotion. 한 번이라도 사용자가 다른 걸 고르면 그 선택 영구 유지.

**기본 엔드포인트 선택 순서**: 세션에 저장된 직전 선택 → `.env` 의 `DEFAULT_PROVIDER` 가 가리키는 첫 엔드포인트 → 리스트 0번째.

**`with_system_prompt=False`**: 본문에 자체 시스템 프롬프트 편집기를 가진 페이지(Prompt Studio)는 이 플래그로 사이드바의 중복 textarea 를 끕니다. 재사용 프롬프트는 사이드바에 임시 슬롯으로 두지 않고 **🧰 Skills 한 곳**에 영구 저장 — 어디서나 드롭다운으로 불러옵니다.

## 상세 문서

- 상위 README: [../../README.md](../../README.md) — 전체 기능 · 보안 정책 · Claude Code skill 비교
- 스크린샷: [../../docs/screenshots/](../../docs/screenshots/)
