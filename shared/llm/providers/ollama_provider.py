"""Ollama provider — local or remote Ollama server.

Also exposes model management (pull/list/delete) since the UI needs it.
"""
from __future__ import annotations

import json
from typing import Iterator

import requests

from ..base import BaseLLMProvider, ChatResponse, Chunk, Message
from ..config import get_secret


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, model: str, base_url: str | None = None, timeout: float = 120.0, **options):
        super().__init__(model, **options)
        self.base_url = (
            base_url
            or get_secret("OLLAMA_BASE_URL")
            or "http://localhost:11434"
        ).rstrip("/")
        self.timeout = timeout

    # ----- chat -----

    def _payload(self, messages: list[Message], stream: bool, **kw) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            **kw,
        }

    def chat(self, messages: list[Message], **kw) -> ChatResponse:
        r = requests.post(
            f"{self.base_url}/api/chat",
            json=self._payload(messages, stream=False, **kw),
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return ChatResponse(
            content=data.get("message", {}).get("content", ""),
            model=data.get("model", self.model),
            usage={
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
            },
            raw=data,
        )

    def stream(self, messages: list[Message], **kw) -> Iterator[Chunk]:
        with requests.post(
            f"{self.base_url}/api/chat",
            json=self._payload(messages, stream=True, **kw),
            stream=True,
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                yield Chunk(
                    delta=data.get("message", {}).get("content", ""),
                    done=bool(data.get("done", False)),
                    raw=data,
                )

    # ----- model management -----

    def list_models(self) -> list[str]:
        return [m["name"] for m in self.list_installed()]

    def list_installed(self) -> list[dict]:
        """Return rich info per installed model: name, size, param_size, quant, modified_at."""
        r = requests.get(f"{self.base_url}/api/tags", timeout=10)
        r.raise_for_status()
        out: list[dict] = []
        for m in r.json().get("models", []):
            details = m.get("details") or {}
            out.append({
                "name":        m.get("name", ""),
                "size":        m.get("size", 0),  # bytes
                "modified_at": m.get("modified_at", ""),
                "param_size":  details.get("parameter_size", ""),
                "quant":       details.get("quantization_level", ""),
                "family":      details.get("family", ""),
            })
        return out

    def pull(self, name: str) -> Iterator[dict]:
        """Stream pull progress events. Each event is a raw dict from Ollama."""
        with requests.post(
            f"{self.base_url}/api/pull",
            json={"name": name, "stream": True},
            stream=True,
            timeout=None,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    yield json.loads(line)

    def delete_model(self, name: str) -> None:
        r = requests.delete(
            f"{self.base_url}/api/delete",
            json={"name": name},
            timeout=30,
        )
        r.raise_for_status()

    def health(self) -> bool:
        try:
            r = requests.get(self.base_url, timeout=2)
            return r.ok
        except requests.RequestException:
            return False
