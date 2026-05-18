"""LiteLLM provider — two modes.

Mode A · Proxy   — when LITELLM_BASE_URL is set.
                   Hits the proxy's OpenAI-compatible REST API directly with
                   `requests`. Does NOT require the `litellm` Python package.
                   Recommended for production / shared key management.

Mode B · SDK     — when LITELLM_BASE_URL is empty.
                   Uses `litellm.completion(...)` for native multi-provider
                   routing based on `model` string prefixes
                   (e.g. "openai/gpt-4o", "anthropic/claude-sonnet-4-6").
                   Requires `pip install 'ai-tools[litellm]'`.
"""
from __future__ import annotations

import json
from typing import Iterator

import requests

from ..base import BaseLLMProvider, ChatResponse, Chunk, Message
from ..config import get_secret


def _normalize_url(url: str | None) -> str | None:
    """Ensure URL has a scheme. Defaults to https:// for bare hostnames."""
    if not url:
        return None
    url = url.strip().rstrip("/")
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


class LiteLLMProvider(BaseLLMProvider):
    name = "litellm"

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
        **options,
    ):
        super().__init__(model, **options)
        self._base_url = _normalize_url(base_url or get_secret("LITELLM_BASE_URL"))
        self._api_key = api_key or get_secret("LITELLM_API_KEY")
        self._proxy_mode = bool(self._base_url)
        self.timeout = timeout

        # SDK mode requires the litellm package; proxy mode does NOT.
        if not self._proxy_mode:
            try:
                import litellm  # noqa: F401
            except ImportError as e:
                raise ImportError(
                    "LiteLLM SDK mode needs the `litellm` package. Either:\n"
                    "  • set LITELLM_BASE_URL to a proxy (no package needed), or\n"
                    "  • install with: pip install 'ai-tools[litellm]'"
                ) from e

    # ------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------

    @staticmethod
    def _msgs(messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    # ------------------------------------------------------------
    # chat / stream — dispatch by mode
    # ------------------------------------------------------------

    def chat(self, messages: list[Message], **kw) -> ChatResponse:
        return self._proxy_chat(messages, **kw) if self._proxy_mode else self._sdk_chat(messages, **kw)

    def stream(self, messages: list[Message], **kw) -> Iterator[Chunk]:
        if self._proxy_mode:
            yield from self._proxy_stream(messages, **kw)
        else:
            yield from self._sdk_stream(messages, **kw)

    # ------------------------------------------------------------
    # PROXY mode (OpenAI-compatible REST)
    # ------------------------------------------------------------

    def _proxy_chat(self, messages: list[Message], **kw) -> ChatResponse:
        r = requests.post(
            f"{self._base_url}/v1/chat/completions",
            headers=self._headers(),
            json={"model": self.model, "messages": self._msgs(messages), "stream": False, **kw},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        return ChatResponse(
            content=choice["message"].get("content", "") or "",
            model=data.get("model", self.model),
            usage=data.get("usage", {}),
            raw=data,
        )

    def _proxy_stream(self, messages: list[Message], **kw) -> Iterator[Chunk]:
        with requests.post(
            f"{self._base_url}/v1/chat/completions",
            headers=self._headers(),
            json={"model": self.model, "messages": self._msgs(messages), "stream": True, **kw},
            stream=True,
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            for raw in r.iter_lines():
                if not raw:
                    continue
                if raw.startswith(b"data: "):
                    payload = raw[6:]
                    if payload.strip() == b"[DONE]":
                        yield Chunk(delta="", done=True)
                        return
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choice = data.get("choices", [{}])[0]
                    delta = (choice.get("delta") or {}).get("content") or ""
                    done = choice.get("finish_reason") is not None
                    yield Chunk(delta=delta, done=done, raw=data)

    # ------------------------------------------------------------
    # SDK mode (litellm package)
    # ------------------------------------------------------------

    def _sdk_chat(self, messages: list[Message], **kw) -> ChatResponse:
        import litellm
        r = litellm.completion(
            model=self.model,
            messages=self._msgs(messages),
            api_key=self._api_key,
            **kw,
        )
        choice = r.choices[0]
        usage = r.usage.model_dump() if hasattr(r.usage, "model_dump") else dict(r.usage or {})
        return ChatResponse(
            content=choice.message.content or "",
            model=r.model,
            usage=usage,
            raw=r.model_dump() if hasattr(r, "model_dump") else None,
        )

    def _sdk_stream(self, messages: list[Message], **kw) -> Iterator[Chunk]:
        import litellm
        stream = litellm.completion(
            model=self.model,
            messages=self._msgs(messages),
            api_key=self._api_key,
            stream=True,
            **kw,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            done = chunk.choices[0].finish_reason is not None
            yield Chunk(delta=delta, done=done)

    # ------------------------------------------------------------
    # list_models — proxy /v1/models OR SDK get_valid_models()
    # ------------------------------------------------------------

    def list_models(self) -> list[str]:
        if self._proxy_mode:
            try:
                r = requests.get(
                    f"{self._base_url}/v1/models",
                    headers=self._headers(),
                    timeout=10,
                )
                r.raise_for_status()
                return sorted(m["id"] for m in r.json().get("data", []))
            except Exception:
                return []  # proxy reachable but listing failed — let user type model manually

        # SDK mode
        try:
            from litellm.utils import get_valid_models
            valid = get_valid_models() or []
            if valid:
                return sorted(valid)
        except Exception:
            pass

        return [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-opus-4-7",
            "gemini/gemini-1.5-pro",
            "ollama/llama3.1",
        ]

    # ------------------------------------------------------------
    # Diagnostics — useful from Settings page
    # ------------------------------------------------------------

    def mode(self) -> str:
        return "proxy" if self._proxy_mode else "sdk"

    def health(self) -> tuple[bool, str]:
        """Proxy mode: try /v1/models. Returns (ok, message)."""
        if not self._proxy_mode:
            return True, "SDK mode (no proxy to check)"
        try:
            r = requests.get(
                f"{self._base_url}/v1/models",
                headers=self._headers(),
                timeout=5,
            )
            if r.ok:
                n = len(r.json().get("data", []))
                return True, f"{n} models from {self._base_url}"
            return False, f"HTTP {r.status_code} from {self._base_url}"
        except requests.RequestException as e:
            return False, f"{type(e).__name__}: {e}"
