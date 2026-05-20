"""Named LLM endpoints — a thin layer on top of factory.get_provider().

An Endpoint is a saved (provider_kind, base_url, api_key_env, default_model)
record with a user-friendly name. resolve(endpoint) constructs a live
BaseLLMProvider via the existing factory — so the four provider implementations
in shared/llm/providers/ stay untouched.

Default endpoints (one per provider) are auto-synthesized from .env at read
time; only user-added endpoints are persisted to endpoints.json.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .base import BaseLLMProvider
from .config import get_secret
from .factory import get_provider, list_providers

ProviderKind = Literal["ollama", "openai", "anthropic", "litellm"]
PROVIDER_KINDS: tuple[ProviderKind, ...] = ("ollama", "openai", "anthropic", "litellm")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")

_PROVIDER_ICONS = {
    "ollama": "🦙",
    "openai": "☁️",
    "anthropic": "🧠",
    "litellm": "⚡",
}

_DEFAULT_NAMES = {
    "ollama": "Ollama (기본)",
    "openai": "OpenAI (기본)",
    "anthropic": "Anthropic (기본)",
    "litellm": "LiteLLM (기본)",
}


@dataclass(frozen=True, slots=True)
class Endpoint:
    slug: str
    name: str
    provider_kind: ProviderKind
    base_url: str | None = None
    api_key_env: str | None = None
    default_model: str | None = None
    extra_options: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    is_default: bool = False
    created_at: str = ""
    updated_at: str = ""

    @property
    def icon(self) -> str:
        return _PROVIDER_ICONS.get(self.provider_kind, "📡")

    def to_dict(self) -> dict:
        return {
            "$schema_version": 1,
            "slug": self.slug,
            "name": self.name,
            "provider_kind": self.provider_kind,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "default_model": self.default_model,
            "extra_options": dict(self.extra_options or {}),
            "enabled": self.enabled,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Endpoint":
        return cls(
            slug=data["slug"],
            name=data.get("name", data["slug"]),
            provider_kind=data["provider_kind"],
            base_url=data.get("base_url"),
            api_key_env=data.get("api_key_env"),
            default_model=data.get("default_model"),
            extra_options=dict(data.get("extra_options") or {}),
            enabled=bool(data.get("enabled", True)),
            is_default=bool(data.get("is_default", False)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


# ============================================================
# Default endpoints — synthesized from .env (never written to disk)
# ============================================================

def default_endpoints() -> list[Endpoint]:
    """Build one default Endpoint per registered provider, reading .env state.

    Synthesized fresh each call so .env edits are reflected immediately.
    """
    out: list[Endpoint] = []
    known = set(list_providers())
    for kind in PROVIDER_KINDS:
        if kind not in known:
            continue
        if kind == "ollama":
            out.append(Endpoint(
                slug="ollama-default",
                name=_DEFAULT_NAMES["ollama"],
                provider_kind="ollama",
                base_url=get_secret("OLLAMA_BASE_URL") or "http://localhost:11434",
                api_key_env=None,
                default_model=get_secret("DEFAULT_MODEL"),
                is_default=True,
            ))
        elif kind == "openai":
            out.append(Endpoint(
                slug="openai-default",
                name=_DEFAULT_NAMES["openai"],
                provider_kind="openai",
                base_url=None,
                api_key_env="OPENAI_API_KEY",
                default_model=get_secret("DEFAULT_MODEL"),
                is_default=True,
            ))
        elif kind == "anthropic":
            out.append(Endpoint(
                slug="anthropic-default",
                name=_DEFAULT_NAMES["anthropic"],
                provider_kind="anthropic",
                base_url=None,
                api_key_env="ANTHROPIC_API_KEY",
                default_model=get_secret("DEFAULT_MODEL"),
                is_default=True,
            ))
        elif kind == "litellm":
            out.append(Endpoint(
                slug="litellm-default",
                name=_DEFAULT_NAMES["litellm"],
                provider_kind="litellm",
                base_url=get_secret("LITELLM_BASE_URL"),
                api_key_env="LITELLM_API_KEY",
                default_model=get_secret("DEFAULT_MODEL"),
                is_default=True,
            ))
    return out


# ============================================================
# Registry — persists user-added endpoints to a single JSON file
# ============================================================

class EndpointRegistry:
    def __init__(self, store_path: Path):
        self.path = Path(store_path)

    # ---------- read ----------

    def _load_custom(self) -> list[Endpoint]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        out: list[Endpoint] = []
        for item in data or []:
            try:
                out.append(Endpoint.from_dict(item))
            except Exception:
                continue
        return out

    def list(self) -> list[Endpoint]:
        """Defaults + customs. Customs with same slug override defaults."""
        defaults = {e.slug: e for e in default_endpoints()}
        for ep in self._load_custom():
            defaults[ep.slug] = ep
        return list(defaults.values())

    def list_custom(self) -> list[Endpoint]:
        return self._load_custom()

    def get(self, slug: str) -> Endpoint | None:
        for ep in self.list():
            if ep.slug == slug:
                return ep
        return None

    # ---------- write ----------

    @staticmethod
    def validate_slug(slug: str) -> None:
        if not _SLUG_RE.match(slug):
            raise ValueError(
                f"슬러그는 소문자·숫자·하이픈만 사용, 1-64자: {slug!r}"
            )

    def save(self, ep: Endpoint) -> Endpoint:
        self.validate_slug(ep.slug)
        if ep.provider_kind not in PROVIDER_KINDS:
            raise ValueError(f"알 수 없는 provider_kind: {ep.provider_kind}")

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        customs = self._load_custom()
        idx = next((i for i, e in enumerate(customs) if e.slug == ep.slug), -1)
        created = customs[idx].created_at if idx >= 0 and customs[idx].created_at else now

        finalized = Endpoint(
            slug=ep.slug,
            name=ep.name,
            provider_kind=ep.provider_kind,
            base_url=ep.base_url or None,
            api_key_env=ep.api_key_env or None,
            default_model=ep.default_model or None,
            extra_options=dict(ep.extra_options or {}),
            enabled=ep.enabled,
            is_default=False,
            created_at=created,
            updated_at=now,
        )
        if idx >= 0:
            customs[idx] = finalized
        else:
            customs.append(finalized)

        self._write(customs)
        return finalized

    def delete(self, slug: str) -> None:
        customs = self._load_custom()
        if not any(e.slug == slug for e in customs):
            # If it's a default, refuse politely
            defaults = {e.slug for e in default_endpoints()}
            if slug in defaults:
                raise ValueError(f"기본 엔드포인트는 삭제할 수 없습니다: {slug}")
            return
        customs = [e for e in customs if e.slug != slug]
        self._write(customs)

    def set_enabled(self, slug: str, enabled: bool) -> None:
        """Toggle enabled flag. For defaults this persists a shim that overrides them."""
        ep = self.get(slug)
        if ep is None:
            raise ValueError(f"엔드포인트를 찾을 수 없음: {slug}")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        shim = Endpoint(
            slug=ep.slug,
            name=ep.name,
            provider_kind=ep.provider_kind,
            base_url=ep.base_url,
            api_key_env=ep.api_key_env,
            default_model=ep.default_model,
            extra_options=dict(ep.extra_options),
            enabled=enabled,
            is_default=False,
            created_at=ep.created_at or now,
            updated_at=now,
        )
        customs = self._load_custom()
        idx = next((i for i, e in enumerate(customs) if e.slug == slug), -1)
        if idx >= 0:
            customs[idx] = shim
        else:
            customs.append(shim)
        self._write(customs)

    def _write(self, customs: list[Endpoint]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps([e.to_dict() for e in customs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)


_registry: EndpointRegistry | None = None


def get_endpoints(store_path: Path | None = None) -> EndpointRegistry:
    """Process-wide singleton."""
    global _registry
    if _registry is None:
        if store_path is None:
            raise RuntimeError("get_endpoints()를 처음 호출할 때 store_path 인자 필요")
        _registry = EndpointRegistry(store_path)
    return _registry


# ============================================================
# resolve — Endpoint → BaseLLMProvider
# ============================================================

def resolve(ep: Endpoint, *, model: str | None = None) -> BaseLLMProvider:
    """Construct a live provider for the endpoint."""
    chosen_model = (model or ep.default_model or "-").strip() or "-"
    kwargs: dict = {"model": chosen_model}

    if ep.provider_kind == "ollama":
        if ep.base_url:
            kwargs["base_url"] = ep.base_url
    elif ep.provider_kind == "litellm":
        if ep.base_url:
            kwargs["base_url"] = ep.base_url
        if ep.api_key_env:
            v = get_secret(ep.api_key_env)
            if v:
                kwargs["api_key"] = v
    elif ep.provider_kind in ("openai", "anthropic"):
        if ep.api_key_env:
            v = get_secret(ep.api_key_env)
            if v:
                kwargs["api_key"] = v

    # extra_options — provider-specific kwargs. Coerce numeric strings.
    for k, v in (ep.extra_options or {}).items():
        if v is None or v == "":
            continue
        if isinstance(v, str) and v.replace(".", "", 1).isdigit():
            try:
                kwargs[k] = float(v) if "." in v else int(v)
            except ValueError:
                kwargs[k] = v
        else:
            kwargs[k] = v

    return get_provider(ep.provider_kind, **kwargs)


# ============================================================
# Diagnostics
# ============================================================

def has_api_key(ep: Endpoint) -> bool:
    if not ep.api_key_env:
        return ep.provider_kind == "ollama"  # ollama doesn't need one
    return bool(get_secret(ep.api_key_env))


def test_connection(ep: Endpoint) -> tuple[bool, str]:
    """Lightweight liveness probe. Returns (ok, human_message)."""
    try:
        provider = resolve(ep)
    except ImportError as e:
        return False, f"패키지 미설치: {e}"
    except RuntimeError as e:
        return False, f"설정 누락: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    try:
        if ep.provider_kind == "ollama":
            ok = bool(getattr(provider, "health", lambda: False)())
            if not ok:
                return False, f"서버 응답 없음: {ep.base_url}"
            n = len(provider.list_models())
            return True, f"OK · 설치 모델 {n}개"
        elif ep.provider_kind == "litellm":
            health = getattr(provider, "health", None)
            if health:
                ok, msg = health()
                return ok, msg
            return True, "SDK 모드 (proxy 확인 불가)"
        else:
            models = provider.list_models()
            return True, f"OK · 모델 {len(models)}개 조회"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
