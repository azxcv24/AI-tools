# AI-tools

다양한 AI / LLM 기술을 활용한 도구들을 모아두는 **공개(public)** 모노레포.

> 큰 카테고리(예: `AI/`)를 두고 그 안에 개별 도구를 둡니다. 카테고리 간 공통 모듈은 [shared/](shared/) 에 둡니다.

---

## 구조

```
AI-tools/
├── README.md             # (this file) 전체 개요 + 보안 정책
├── .gitignore            # 비밀/데이터/모델 노출 차단
├── .env.example          # 환경변수 템플릿 (실제 값 없음)
│
├── shared/               # 프로젝트 전반에서 재사용하는 모듈
│   ├── llm/              # LLM provider 추상화 (OpenAI / Anthropic / Ollama / LiteLLM ...)
│   ├── storage/          # 파일 / 결과물 저장 추상화 (Excel, Markdown ...)
│   └── execution/        # 로컬 / 원격 (RTX 5090, Spark) 실행기
│
└── AI/                   # AI / LLM 도구 카테고리 — 상세 계획은 AI/README.md
    └── llm-studio/       # Streamlit 기반 LLM 플레이그라운드
```

향후 다른 카테고리(예: `Web/`, `DevOps/`, `Data/` …)가 추가될 수 있으며, 모두 [shared/](shared/) 를 가져다 씁니다.

---

## 🔐 보안 정책 (반드시 준수)

이 저장소는 **공개(public)** 입니다. 한 번 커밋된 비밀은 force-push 로도 완전히 지우기 어렵습니다. 다음을 반드시 지킵니다:

### 절대 커밋 금지
- **API 키 / 토큰 / 비밀번호 / 접속정보**
- **사용자 업로드 파일, 모델 가중치, 데이터셋**
- `.env`, `*.key`, `*.pem`, `secrets/`, `credentials/`
- `.streamlit/secrets.toml`

이미 [.gitignore](.gitignore) 가 위 항목들을 차단하지만, 그래도 매 커밋마다 확인합니다.

### 비밀 값을 다루는 방법
1. **저장**: `.env` 파일에 저장. `.env` 는 gitignore 됨.
2. **선언**: 새 비밀 키가 필요하면 [.env.example](.env.example) 에 **키 이름만** (값 없이) 추가.
3. **로드**: 코드 안에서는 `shared/llm/config.py` 의 `get_secret("KEY_NAME")` 만 사용. 하드코딩 금지.
4. **표시**: UI 에 비밀을 표시할 때는 항상 마스킹 (`sk-...abcd`).

### 커밋 전 체크
```bash
git diff --staged | grep -iE 'api.?key|secret|token|password|sk-[a-z0-9]'
```
출력이 있으면 커밋 중단.

### 사고 대응
실수로 비밀을 커밋했다면:
1. **즉시 해당 키를 발급처에서 무효화** (rotate).
2. `git filter-repo` 또는 BFG 로 히스토리에서 제거.
3. 강제 푸시 후, 협업자에게 다시 클론하도록 공지.

> 키를 무효화하는 것이 히스토리 제거보다 우선합니다. 공개 저장소에 푸시된 순간 자동 봇이 키를 수집했다고 가정해야 합니다.

---

## 시작하기

```bash
# 1) 환경변수 준비
cp .env.example .env
# .env 를 열어 사용할 provider 의 키만 채웁니다.

# 2) 각 도구별 README 참조
```

- [AI/README.md](AI/README.md) — AI 카테고리 상세 계획 & 단계별 로드맵
- [shared/](shared/) — 공용 모듈 (LLM 게이트웨이, 파일, 원격 실행기)

---

## 기여 가이드 (요약)

- 새 도구 = 카테고리 폴더 안에 새 하위 폴더 (예: `AI/my-new-tool/`).
- 공용 로직은 반드시 [shared/](shared/) 로 추출 — 카테고리 간 코드 중복 금지.
- PR 전 [.gitignore](.gitignore) 가 새 데이터/비밀 경로를 커버하는지 확인.

## 라이선스

(TBD)
