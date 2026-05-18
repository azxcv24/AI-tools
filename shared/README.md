# shared/

프로젝트 전반에서 재사용하는 모듈. 어떤 카테고리(`AI/`, 향후 `Web/`, `DevOps/` …)도 여기를 import 합니다.

## 모듈

```
shared/
├── llm/              # LLM provider 추상화
│   ├── base.py       # BaseLLMProvider + Message / ChatResponse / Chunk
│   ├── config.py     # .env 로드 + get_secret / mask_secret
│   ├── factory.py    # get_provider(name, **kw) — 지연 로딩
│   └── providers/
│       ├── ollama_provider.py     # 로컬/원격 Ollama (+ pull/list/delete)
│       ├── openai_provider.py     # 옵셔널: pip install 'ai-tools[openai]'
│       ├── anthropic_provider.py  # 옵셔널: pip install 'ai-tools[anthropic]'
│       └── litellm_provider.py    # 게이트웨이: pip install 'ai-tools[litellm]'
└── storage/
    └── files.py      # FileManager — 단일 루트, traversal 방지
```

## 사용법

```python
from shared.llm import get_provider, Message

llm = get_provider("ollama",    model="llama3.1")
llm = get_provider("openai",    model="gpt-4o")
llm = get_provider("anthropic", model="claude-sonnet-4-6")
llm = get_provider("litellm",   model="anthropic/claude-sonnet-4-6")  # 게이트웨이

# 동기
resp = llm.chat([Message(role="user", content="Hello")])
print(resp.content)

# 스트리밍
for chunk in llm.stream([Message(role="user", content="Hello")]):
    print(chunk.delta, end="", flush=True)
```

```python
from shared.storage import FileManager

fm = FileManager("./uploads")
fm.save("note.md", b"# hello")
for info in fm.list():
    print(info.name, info.size)
fm.delete("note.md")
```

## 새 provider 추가

1. `shared/llm/providers/<name>_provider.py` 생성. `BaseLLMProvider` 상속, `chat / stream / list_models` 구현.
2. 키가 필요하면 `from ..config import get_secret` 으로만 읽기. **하드코딩 금지.**
3. [`factory.py`](llm/factory.py) 의 `_PROVIDERS` 에 등록 (또는 런타임에 `register_provider()`).
4. 옵셔널 의존성이라면 import 를 `__init__` 안에서 try/except 하여 친절한 에러 메시지 제공.

## 보안 원칙

- `os.environ` 직접 접근 금지 — `config.get_secret()` 만 사용 (단일 chokepoint).
- 비밀 값을 로그 / 예외 메시지에 넣지 말 것.
- `FileManager` 는 root 밖 경로 접근을 모두 거부 — 직접 `open()` 으로 사용자 입력 경로 열지 말 것.
