"""Skill = reusable bundle of (system prompt + user-prompt template + page target).

A Skill pairs a Persona-style system prompt with an optional Jinja-ish user
prompt template, plus metadata that lets pages filter to skills they can run
(e.g. Excel Agent only shows skills with kind="excel-pandas"). Stored as JSON
on disk; seed skills are hardcoded in seeds.py and carry readonly=True.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

SkillKind = Literal["chat-system", "excel-pandas", "excel-structure", "prompt-enhance"]
SKILL_KINDS: tuple[SkillKind, ...] = (
    "chat-system",
    "excel-pandas",
    "excel-structure",
    "prompt-enhance",
)


@dataclass(frozen=True, slots=True)
class Skill:
    slug: str
    name: str
    icon: str
    kind: SkillKind
    description: str
    system_prompt: str
    user_prompt_template: str = ""
    tags: tuple[str, ...] = ()
    default_endpoint: str | None = None
    default_model: str | None = None
    sample_files: tuple[str, ...] = ()
    readonly: bool = False
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "$schema_version": 1,
            "slug": self.slug,
            "name": self.name,
            "icon": self.icon,
            "kind": self.kind,
            "description": self.description,
            "tags": list(self.tags),
            "system_prompt": self.system_prompt,
            "user_prompt_template": self.user_prompt_template,
            "default_endpoint": self.default_endpoint,
            "default_model": self.default_model,
            "sample_files": list(self.sample_files),
            "readonly": self.readonly,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        return cls(
            slug=data["slug"],
            name=data.get("name", data["slug"]),
            icon=data.get("icon", "🧩"),
            kind=data.get("kind", "chat-system"),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            user_prompt_template=data.get("user_prompt_template", ""),
            tags=tuple(data.get("tags") or ()),
            default_endpoint=data.get("default_endpoint"),
            default_model=data.get("default_model"),
            sample_files=tuple(data.get("sample_files") or ()),
            readonly=bool(data.get("readonly", False)),
            version=int(data.get("version", 1)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class _SafeDict(defaultdict):
    """str.format_map source that returns '' for any missing key."""

    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return ""


def render_template(template: str, **values: object) -> str:
    """Safe str.format substitution — missing keys become empty strings.

    Avoids KeyError when a template references a placeholder that the caller
    didn't provide (e.g. {schema_json} when structure detection was skipped).
    """
    if not template:
        return ""
    safe: _SafeDict = _SafeDict(str)
    for k, v in values.items():
        safe[k] = "" if v is None else str(v)
    try:
        return template.format_map(safe)
    except Exception:
        return template
