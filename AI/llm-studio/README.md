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
| 💬 Chat            | 사이드바: 엔드포인트·모델·🧰 스킬·시스템 프롬프트·📎 첨부. 본문: 스트리밍 대화 + `.md` 익스포트 |
| 📁 Files           | 파일 업로드 · 리스트 · 다운로드 · 삭제 (경로-안전 FileManager) |
| 🦙 Ollama          | 모델 pull(진행률) · 설치 리스트 · 삭제 · `?endpoint=<slug>` 로 다중 서버 |
| ⚙️ Settings        | **📡 연결 지점 (Endpoints)** + .env 편집(편집 모드 토글, 0600) |
| 📊 Excel Agent     | 구조 자동 인식 → 스킬 적용 → pandas 코드 → 격리 실행 → 스킬로 저장 |
| ✨ Prompt Studio   | 라이브러리(=chat-system 스킬) + 한 줄 → system prompt 향상 + 스킬로 저장 |
| 🧰 Skills          | 시드 13개 + 사용자 스킬 CRUD (kind 필터, 검색, 복제) |

업로드 파일·사용자 스킬·endpoints.json 은 모두 `AI/llm-studio/data/` 에 저장 (전 경로 gitignored).

## 구조

```
llm-studio/
├── app.py                    · 랜딩 + 엔드포인트 상태
├── _bootstrap.py             · sys.path + data dir + SkillRegistry/EndpointRegistry 와이어업
├── components/
│   ├── ui.py                 · header · badge · empty_state · section · sidebar_brand
│   └── sidebar.py            · render_sidebar(page_id, kinds, with_task, with_limits)
├── pages/
│   ├── 1_💬_Chat.py
│   ├── 2_📁_Files.py
│   ├── 3_🦙_Ollama.py
│   ├── 4_⚙️_Settings.py
│   ├── 5_📊_Excel_Agent.py
│   ├── 6_✨_Prompt_Studio.py
│   └── 7_🧰_Skills.py
└── data/                     · uploads · outputs · skills · endpoints.json (gitignored)
```

## 사이드바 공유 컴포넌트

거의 모든 페이지가 동일한 사이드바 골격을 쓰도록 [`components/sidebar.py`](components/sidebar.py) 가 통합. 호출 1줄로 대체:

```python
from components import render_sidebar

state = render_sidebar(
    "excel-agent",
    kinds=["excel-pandas"],   # 사이드바 스킬 드롭다운에 보일 kind
    with_task=True,           # 🛠 작업 설명 textarea
    with_limits=True,         # 🔒 타임아웃·메모리 슬라이더
)

# state.endpoint, state.model, state.skill, state.system_prompt, state.task,
# state.timeout_seconds, state.memory_mb
```

## 상세 문서

- 상위 README: [../../README.md](../../README.md) — 전체 기능 · 보안 정책 · Claude Code skill 비교
- 스크린샷: [../../docs/screenshots/](../../docs/screenshots/)
