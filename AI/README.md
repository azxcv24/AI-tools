# AI 카테고리

AI / LLM 기술을 활용하는 도구들의 모음. 첫 번째 도구는 **Streamlit 기반 LLM Studio** ([llm-studio/](llm-studio/)).

> 보안 정책은 [최상위 README](../README.md#-보안-정책-반드시-준수) 를 따릅니다. 이 카테고리에서 추가로 지킬 사항은 본 문서 하단 [보안 체크리스트](#보안-체크리스트) 참조.

---

## 목표 요구사항

이 카테고리에서 만들 도구들이 충족해야 하는 사용자 요구:

1. **Streamlit 기반 AI 모델 프롬프트** — 대화형 채팅 UI
2. **Streamlit 기반 파일 업로드 / 접근 / 삭제** — 업로드된 파일을 리스트로 보고, 다시 다운로드하거나 삭제
3. **AI 모델 다운로드 및 실행** — Ollama 모델 pull / 실행, 원격 서버 실행 포함
4. **Ollama 프레임워크 통합** — 로컬 / 원격 Ollama 서버 연결, Streamlit 안에서 이미지 다운로드 트리거 → 확인 → 실행
5. **프롬프트 결과 전송 및 저장** — 결과를 파일로 저장하거나 외부로 전송
6. **MD 파일 저장 및 전송** — 결과를 마크다운으로 익스포트

### 추가 비기능 요구사항

- LLM 호출은 **모듈화** — OpenAI / Anthropic / Google / Ollama / **LiteLLM 게이트웨이** / 그 외 상용 API 를 **동일 인터페이스** 로 호출.
- 파일 처리 / 저장 / 실행도 추상화.
- **원격 GPU 서버 (RTX 5090, Spark)** 에서의 실행 지원.
- 엑셀 등 표 데이터: 여러 파일을 프롬프트로 통합 / 연산. (예: "5개 엑셀 파일을 1개로 통합, 동일 표 항목은 평균값으로")
- 너무 복잡한 추상화는 지양. **최소한의 인터페이스 + 충분한 확장점**.

---

## 아키텍처

```
shared/llm/             ← LLM provider 추상화 (BaseProvider + Factory)
   ├─ base.py           ← BaseLLMProvider (chat, stream, list_models)
   ├─ factory.py        ← get_provider("ollama" | "openai" | "anthropic" | "litellm")
   ├─ config.py         ← .env 로부터 비밀 로드 (get_secret)
   └─ providers/
        ├─ openai_provider.py
        ├─ anthropic_provider.py
        ├─ google_provider.py
        ├─ ollama_provider.py     ← + pull / list / delete 모델 관리 API
        └─ litellm_provider.py    ← 단일 진입점 게이트웨이

shared/storage/         ← 파일 / 결과물 저장 추상화
   ├─ files.py          ← 업로드 / 리스트 / 삭제 (FileManager)
   └─ handlers/
        ├─ excel.py     ← pandas 기반 read/write/merge
        └─ markdown.py  ← 결과 → .md 익스포트

shared/execution/       ← 모델 실행 위치 추상화
   ├─ local.py
   └─ remote.py         ← RTX 5090 / Spark 등 (SSH / HTTP RPC)

AI/llm-studio/          ← Streamlit 애플리케이션 (이 카테고리의 첫 도구)
   ├─ app.py            ← 진입점
   ├─ pages/
   │    ├─ 1_💬_Chat.py         ← 요구사항 1 (대화형 프롬프트)
   │    ├─ 2_📁_Files.py        ← 요구사항 2 (업로드/리스트/삭제)
   │    ├─ 3_🦙_Ollama.py       ← 요구사항 3, 4 (모델 다운로드/실행)
   │    ├─ 4_📊_Excel_Tools.py  ← 엑셀 통합/연산 (예시 시나리오)
   │    ├─ 5_📤_Export.py       ← 요구사항 5, 6 (저장 / 전송 / MD)
   │    └─ 6_⚙️_Settings.py     ← provider 선택, 원격 서버 설정
   ├─ components/       ← 재사용 UI 위젯
   └─ data/             ← (gitignored) 업로드 / 출력
```

### LLM provider 인터페이스 (계획)

```python
# shared/llm/base.py (계획 — 실제 구현 시 약간 조정 가능)
class BaseLLMProvider:
    def chat(self, messages: list[Message], **kw) -> ChatResponse: ...
    def stream(self, messages: list[Message], **kw) -> Iterator[Chunk]: ...
    def list_models(self) -> list[str]: ...

# 사용 측 — 어떤 provider 든 동일:
from shared.llm import get_provider

llm = get_provider("ollama",   model="llama3.1")
llm = get_provider("openai",   model="gpt-4o")
llm = get_provider("anthropic", model="claude-sonnet-4-6")
llm = get_provider("litellm",  model="anthropic/claude-sonnet-4-6")  # 게이트웨이

response = llm.chat([{"role": "user", "content": "Hello"}])
```

LiteLLM provider 는 위 모든 모델을 단일 진입점으로 라우팅하는 옵션 — 사용자가 셋팅에서 선택.

### Ollama 통합 흐름 (요구사항 3 + 4)

```
Streamlit (3_🦙_Ollama.py)
    │
    ├─ [모델 풀] 사용자가 "llama3.1" 입력 → POST /api/pull (progress stream)
    │       └─ 진행률 progress bar 로 표시
    │
    ├─ [설치된 모델 리스트] GET /api/tags
    ├─ [모델 삭제] DELETE /api/delete
    └─ [실행] 선택한 모델로 Chat 페이지에서 즉시 사용 가능
```

`shared/llm/providers/ollama_provider.py` 가 위 모든 엔드포인트를 래핑.

### 엑셀 처리 흐름 (요구사항 예시 시나리오)

```
사용자: "5개 엑셀 파일 업로드 → 1개로 통합, 동일 표 항목은 평균"

[Files 페이지에서 5개 업로드]
       │
       ▼
[Excel_Tools 페이지]
   1. LLM 에게 작업 설명 + 각 파일 스키마(헤더) 전달
   2. LLM 이 pandas 코드 생성
   3. 격리된 환경에서 코드 실행 (sandbox)
   4. 결과 미리보기 + 다운로드 (xlsx / csv / md)
```

> ⚠️ LLM 이 생성한 코드는 절대 신뢰 환경에서 실행하지 않습니다. 별도 프로세스 + 화이트리스트 모듈만 import 허용.

---

## 단계별 로드맵

### Phase 1 — Foundation 🔒
보안 + 모듈 골격. **이 단계 이전에는 어떤 키도 코드에 들이지 않습니다.**
- [ ] [.gitignore](../.gitignore), [.env.example](../.env.example) 정비 — **완료**
- [ ] `shared/llm/base.py` — BaseLLMProvider 인터페이스
- [ ] `shared/llm/config.py` — `.env` 로드 + `get_secret()` (마스킹 포함)
- [ ] `shared/llm/factory.py` — `get_provider(name, **kw)`
- [ ] 최소 1개 provider 구현: **Ollama** (키 불필요 → 시작용으로 가장 안전)
- [ ] `shared/storage/files.py` — FileManager (upload/list/delete)
- [ ] `pyproject.toml` 의존성 정리 (streamlit, requests, pandas, openpyxl, python-dotenv)

### Phase 2 — LLM Studio MVP
- [ ] `AI/llm-studio/app.py` 진입점 + 사이드바
- [ ] `1_💬_Chat.py` — provider/model 선택 + 대화 (스트리밍)
- [ ] `2_📁_Files.py` — 업로드 / 리스트 / 삭제 / 다운로드
- [ ] `6_⚙️_Settings.py` — provider 선택, 환경값 확인 (마스킹)
- [ ] 결과 → `.md` 다운로드 (요구사항 6)

### Phase 3 — Provider 확장
- [ ] OpenAI provider
- [ ] Anthropic provider
- [ ] Google (Gemini) provider
- [ ] **LiteLLM gateway provider** — 위 전부를 단일 진입점으로

### Phase 4 — Ollama 통합 (요구사항 3, 4)
- [ ] `3_🦙_Ollama.py` 페이지
- [ ] `ollama pull` 트리거 + 진행률 표시
- [ ] 설치 모델 리스트 / 삭제
- [ ] 로컬 / 원격 Ollama 서버 전환

### Phase 5 — Excel / 표 데이터 도구
- [ ] `4_📊_Excel_Tools.py` 페이지
- [ ] 다중 파일 업로드 + 스키마 미리보기
- [ ] 프롬프트 → LLM → pandas 코드 → sandbox 실행
- [ ] 예시 시나리오 (5개 통합 + 평균) end-to-end 데모

### Phase 6 — 원격 실행 (RTX 5090, Spark)
- [ ] `shared/execution/remote.py` — SSH 또는 HTTP RPC 클라이언트
- [ ] `.env` 에 원격 서버 설정 (`REMOTE_GPU_HOST` 등)
- [ ] Settings 페이지에서 "로컬 / 원격" 토글
- [ ] 작업 디스패치 + 진행상황 폴링

### Phase 7 — 결과 전송 (요구사항 5)
- [ ] `5_📤_Export.py` 페이지
- [ ] 파일로 저장 (md / xlsx / json)
- [ ] 외부 전송 — 이메일, Slack, webhook (필요 시 확장)

### Phase 8 — 운영 / 품질
- [ ] Streamlit auth (배포 시 필수)
- [ ] 로깅 (비밀은 절대 로그에 남기지 않음)
- [ ] 단위 테스트 (provider 인터페이스 conformance test)
- [ ] CI (lint + test + .env 누출 스캔)

---

## 보안 체크리스트

카테고리 내 모든 도구 공통:

- [ ] API 키는 코드에 절대 등장 X — `shared/llm/config.get_secret()` 만 사용
- [ ] 업로드된 사용자 파일은 `AI/llm-studio/data/uploads/` (gitignored) 에만 저장
- [ ] **LLM 이 생성한 코드 실행 시 sandbox 필수** — 별도 프로세스 + 모듈 화이트리스트
- [ ] UI 에 비밀 표시 시 마스킹 (예: `sk-...abcd`, 끝 4자만)
- [ ] 외부 전송 기능은 화이트리스트된 목적지로만
- [ ] 원격 서버 접속은 토큰/키 기반 (비밀번호 사용 금지)
- [ ] 로그에 프롬프트 본문 / 응답 본문 / 비밀 절대 기록 금지 (메타데이터만)
