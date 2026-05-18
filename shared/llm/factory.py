"""Lazy provider factory. Importing a missing optional dep is deferred to instantiation."""
from __future__ import annotations

import importlib

from .base import BaseLLMProvider

# name -> (module path relative to shared.llm, class name)
_PROVIDERS: dict[str, tuple[str, str]] = {
    "ollama":    (".providers.ollama_provider",    "OllamaProvider"),
    "openai":    (".providers.openai_provider",    "OpenAIProvider"),
    "anthropic": (".providers.anthropic_provider", "AnthropicProvider"),
    "litellm":   (".providers.litellm_provider",   "LiteLLMProvider"),
}


def list_providers() -> list[str]:
    return list(_PROVIDERS)


def register_provider(name: str, module: str, class_name: str) -> None:
    """Plug in a new provider without modifying this file."""
    _PROVIDERS[name] = (module, class_name)


def get_provider(name: str, **kwargs) -> BaseLLMProvider:
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider {name!r}. Known: {list(_PROVIDERS)}")
    module_path, class_name = _PROVIDERS[name]
    module = importlib.import_module(module_path, package=__package__)
    cls = getattr(module, class_name)
    return cls(**kwargs)
