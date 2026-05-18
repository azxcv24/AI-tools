"""Anthropic provider. Requires `anthropic>=0.40` (install via `pip install ai-tools[anthropic]`)."""
from __future__ import annotations

from typing import Iterator

from ..base import BaseLLMProvider, ChatResponse, Chunk, Message
from ..config import get_secret


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        max_tokens: int = 4096,
        **options,
    ):
        super().__init__(model, **options)
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package not installed. Run: pip install 'ai-tools[anthropic]'"
            ) from e

        key = api_key or get_secret("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (.env)")
        self._client = Anthropic(api_key=key)
        self.max_tokens = max_tokens

    @staticmethod
    def _split(messages: list[Message]) -> tuple[str, list[dict]]:
        """Anthropic takes `system` as a top-level param, not in messages."""
        system = ""
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                system = (system + "\n" + m.content).strip() if system else m.content
            else:
                out.append({"role": m.role, "content": m.content})
        return system, out

    def chat(self, messages: list[Message], **kw) -> ChatResponse:
        system, msgs = self._split(messages)
        r = self._client.messages.create(
            model=self.model,
            max_tokens=kw.pop("max_tokens", self.max_tokens),
            system=system or None,
            messages=msgs,
            **kw,
        )
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return ChatResponse(
            content=text,
            model=r.model,
            usage={"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens},
            raw=r.model_dump(),
        )

    def stream(self, messages: list[Message], **kw) -> Iterator[Chunk]:
        system, msgs = self._split(messages)
        with self._client.messages.stream(
            model=self.model,
            max_tokens=kw.pop("max_tokens", self.max_tokens),
            system=system or None,
            messages=msgs,
            **kw,
        ) as stream:
            for text in stream.text_stream:
                yield Chunk(delta=text, done=False)
        yield Chunk(delta="", done=True)

    def list_models(self) -> list[str]:
        try:
            page = self._client.models.list(limit=100)
            return sorted(m.id for m in page.data)
        except Exception:
            # SDK / API 호출 실패 시 최소 fallback
            return [
                "claude-opus-4-7",
                "claude-sonnet-4-6",
                "claude-haiku-4-5-20251001",
            ]
