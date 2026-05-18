# LLM Studio

Streamlit 기반 LLM 플레이그라운드. AI 카테고리의 첫 번째 도구.

## 실행

```bash
# 1) 의존성 설치 (프로젝트 루트에서)
pip install -e .
# provider 별 옵셔널:
pip install -e '.[openai]'      # OpenAI
pip install -e '.[anthropic]'   # Anthropic
pip install -e '.[litellm]'     # LiteLLM 게이트웨이
pip install -e '.[all]'         # 전부

# 2) 환경변수 설정
cp .env.example .env            # 루트의 .env 를 채움
# .env 는 gitignored — 절대 커밋 X

# 3) Streamlit 실행
cd AI/llm-studio
streamlit run app.py
```

브라우저에서 [http://localhost:8501](http://localhost:8501) 열림.

## 페이지

| 페이지 | 기능 | 요구사항 매핑 |
|---|---|---|
| 💬 Chat     | Provider / 모델 선택 → 스트리밍 대화 → `.md` 다운로드 | 1, 5, 6 |
| 📁 Files    | 파일 업로드 · 리스트 · 다운로드 · 삭제                 | 2 |
| 🦙 Ollama   | 모델 pull (진행률) · 설치 리스트 · 삭제                 | 3, 4 |
| ⚙️ Settings | 등록된 provider · 환경변수 상태 (마스킹)                | — |

업로드된 파일은 `AI/llm-studio/data/uploads/` 에 저장됩니다 (전 경로 gitignored).

## 구조

```
llm-studio/
├── app.py              # Streamlit 진입점
├── _bootstrap.py       # sys.path + data dir 셋업
├── pages/              # Streamlit 멀티페이지
│   ├── 1_💬_Chat.py
│   ├── 2_📁_Files.py
│   ├── 3_🦙_Ollama.py
│   └── 4_⚙️_Settings.py
├── components/         # (예정) 재사용 위젯
└── data/               # 업로드 / 출력 (gitignored)
```

## 남은 작업 (이 도구 한정)

다음은 [상위 카테고리 계획](../README.md#단계별-로드맵) 의 일부를 이 도구에 매핑한 것:

- **Phase 5** — Excel 도구 페이지 (`5_📊_Excel_Tools.py`): 다중 업로드 → 프롬프트 → pandas 코드 생성 → sandbox 실행
- **Phase 6** — 원격 실행 토글 (Settings 페이지에서 로컬/원격 전환)
- **Phase 7** — 외부 전송 페이지 (이메일 / Slack / webhook)
- **Phase 8** — `streamlit_authenticator` 로 액세스 제어
