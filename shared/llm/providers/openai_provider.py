"""OpenAI provider. Requires `openai>=1.50` (install via `pip install ai-tools[openai]`)."""
from __future__ import annotations

from typing import Iterator

from ..base import BaseLLMProvider, ChatResponse, Chunk, Message
from ..config import get_secret


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None, **options):
        super().__init__(model, **options)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "openai package not installed. Run: pip install 'ai-tools[openai]'"
            ) from e

        key = api_key or get_secret("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set (.env)")
        self._client = OpenAI(api_key=key, organization=get_secret("OPENAI_ORG_ID"))

    def _msgs(self, messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def chat(self, messages: list[Message], **kw) -> ChatResponse:
        r = self._client.chat.completions.create(
            model=self.model, messages=self._msgs(messages), **kw
        )
        choice = r.choices[0]
        return ChatResponse(
            content=choice.message.content or "",
            model=r.model,
            usage=r.usage.model_dump() if r.usage else {},
            raw=r.model_dump(),
        )

    def stream(self, messages: list[Message], **kw) -> Iterator[Chunk]:
        stream = self._client.chat.completions.create(
            model=self.model, messages=self._msgs(messages), stream=True, **kw
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            done = chunk.choices[0].finish_reason is not None
            yield Chunk(delta=delta, done=done, raw=chunk.model_dump())

    def list_models(self) -> list[str]:
        """Return chat-capable models only (excludes embedding / whisper / tts / dall-e / ...)."""
        try:
            ids = [m.id for m in self._client.models.list().data]
        except Exception:
            return []
        skip = ("embedding", "whisper", "tts", "dall-e", "audio", "moderation", "davinci-002", "babbage-002", "-instruct")
        chat = [m for m in ids if not any(s in m.lower() for s in skip)]
        return sorted(chat)
