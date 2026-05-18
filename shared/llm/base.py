from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    role: Role
    content: str


@dataclass
class ChatResponse:
    content: str
    model: str
    usage: dict = field(default_factory=dict)
    raw: dict | None = None


@dataclass
class Chunk:
    delta: str
    done: bool = False
    raw: dict | None = None


class BaseLLMProvider(ABC):
    name: str = ""

    def __init__(self, model: str, **options):
        self.model = model
        self.options = options

    @abstractmethod
    def chat(self, messages: list[Message], **kw) -> ChatResponse: ...

    @abstractmethod
    def stream(self, messages: list[Message], **kw) -> Iterator[Chunk]: ...

    @abstractmethod
    def list_models(self) -> list[str]: ...

    def __repr__(self) -> str:
        return f"<{type(self).__name__} model={self.model!r}>"
