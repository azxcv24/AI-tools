# Screenshots

이 폴더에는 README 에 들어갈 실행 화면 이미지를 둡니다.

## 캡처 방법

```bash
cd AI/llm-studio
streamlit run app.py
```

브라우저에서 [http://localhost:8501](http://localhost:8501) 열고, 각 페이지를 캡처해서 다음 이름으로 저장:

| 파일명 | 페이지 |
|---|---|
| `01-landing.png` | 🧪 랜딩 (엔드포인트 상태 + 페이지 카드 5개) |
| `02-chat.png` | 💬 Chat — ChatGPT 스타일 통합 UI (사이드바 + 파일 드롭존 + 채팅 입력) |
| `03-prompt-studio.png` | ✨ Prompt Studio (페르소나 라이브러리 + 향상기) |
| `04-skills.png` | 🧰 Skills (스킬 CRUD 목록) |
| `05-ollama.png` | 🦙 Ollama (설치 모델 + 인기 픽 탭) |
| `06-settings.png` | ⚙️ Settings (📡 연결 지점 + .env 편집) |

권장 해상도: 1600 × 1100 (playwright 로 자동 캡처 권장 — `/tmp/shoot.py` 참고).

## 주의

- **API 키 / `.env` 내용이 화면에 보이지 않도록**:
  - Settings 페이지는 편집 모드 OFF 상태 캡처 (자동 마스킹됨)
  - 내부 IP·도메인은 Pillow 후처리로 박스 가림 (`/tmp/redact_v2.py`)
- 채팅 내용에 개인정보 / 실 데이터 포함되지 않도록.
