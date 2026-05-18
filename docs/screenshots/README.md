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
| `01-landing.png` | 🧪 랜딩 (시스템 상태 + 페이지 카드) |
| `02-chat.png` | 💬 Chat (대화 중, 파일 첨부 배지 보이게) |
| `03-files.png` | 📁 Files (파일 몇 개 업로드된 상태) |
| `04-ollama.png` | 🦙 Ollama (설치 모델 + 인기 픽 탭) |
| `05-excel-agent.png` | 📊 Excel Agent (스키마 + 생성된 코드 + 결과) |
| `06-prompt-studio.png` | ✨ Prompt Studio (페르소나 선택 + 향상 결과) |
| `07-settings.png` | ⚙️ Settings (편집 모드 ON 상태, 값 마스킹) |

권장 캡처 해상도: 가로 1400~1600px (Retina 캡처면 OK).

## 주의

- **API 키 / `.env` 내용이 화면에 보이지 않도록** 캡처 전에 Settings 페이지를 떠나거나 마스킹 확인.
- 채팅 내용에 개인정보 / 실 데이터 포함되지 않도록.
