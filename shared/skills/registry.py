"""JSON-backed CRUD store for user Skills (seeds stay in code).

One JSON file per user skill at <skills_dir>/<slug>.json — chosen so git
diffs and manual edits stay per-skill. The registry's list() merges hardcoded
SEED_SKILLS with whatever is on disk; if a user file shares a slug with a
seed, the user file wins (lets users override seed wording).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import Skill, SkillKind
from .seeds import SEED_SKILLS, SEED_SKILLS_BY_SLUG

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")


class ReadOnlySkillError(Exception):
    """Raised when trying to mutate a seed (readonly) skill."""


class SkillRegistry:
    def __init__(self, skills_dir: Path):
        self.dir = Path(skills_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---------- read ----------

    def list(self) -> list[Skill]:
        """All skills — user files override seeds with the same slug."""
        user_by_slug: dict[str, Skill] = {}
        for path in sorted(self.dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                skill = Skill.from_dict(data)
                user_by_slug[skill.slug] = skill
            except Exception:
                continue
        merged: dict[str, Skill] = dict(SEED_SKILLS_BY_SLUG)
        merged.update(user_by_slug)

        def sort_key(s: Skill) -> tuple:
            # readonly seeds first within their kind; then by updated_at desc
            return (not s.readonly, s.kind, -self._ts_rank(s.updated_at), s.name)

        return sorted(merged.values(), key=sort_key)

    @staticmethod
    def _ts_rank(iso: str) -> int:
        try:
            return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
        except Exception:
            return 0

    def get(self, slug: str) -> Skill | None:
        # User file wins if both exist
        path = self.dir / f"{slug}.json"
        if path.exists():
            try:
                return Skill.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return SEED_SKILLS_BY_SLUG.get(slug)

    def by_kind(self, *kinds: SkillKind) -> list[Skill]:
        if not kinds:
            return self.list()
        wanted = set(kinds)
        return [s for s in self.list() if s.kind in wanted]

    # ---------- write ----------

    @staticmethod
    def validate_slug(slug: str) -> None:
        if not _SLUG_RE.match(slug):
            raise ValueError(
                f"슬러그는 소문자·숫자·하이픈만 사용, 1-64자: {slug!r}"
            )

    def save(self, skill: Skill, *, force: bool = False) -> Skill:
        """Write skill to disk. Refuses to write a readonly seed unless force=True."""
        self.validate_slug(skill.slug)
        if not force and skill.slug in SEED_SKILLS_BY_SLUG and (
            self.dir / f"{skill.slug}.json"
        ).exists() is False:
            # First write for a slug that matches a seed → allow (acts as override)
            pass

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prev = self.get(skill.slug)
        version = (prev.version + 1) if prev and not prev.readonly else 1
        created = prev.created_at if prev and prev.created_at else now

        # Force user copies to be writable
        finalized = Skill(
            slug=skill.slug,
            name=skill.name,
            icon=skill.icon or "🧩",
            kind=skill.kind,
            description=skill.description,
            system_prompt=skill.system_prompt,
            user_prompt_template=skill.user_prompt_template,
            tags=tuple(skill.tags),
            default_endpoint=skill.default_endpoint,
            default_model=skill.default_model,
            sample_files=tuple(skill.sample_files),
            readonly=False,
            version=version,
            created_at=created,
            updated_at=now,
        )

        path = self.dir / f"{finalized.slug}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(finalized.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return finalized

    def delete(self, slug: str) -> None:
        """Delete a user skill. Cannot delete a seed."""
        path = self.dir / f"{slug}.json"
        if not path.exists():
            if slug in SEED_SKILLS_BY_SLUG:
                raise ReadOnlySkillError(f"시드 스킬은 삭제할 수 없습니다: {slug}")
            return
        path.unlink()

    def clone(self, src_slug: str, new_slug: str, *, name_suffix: str = " (사본)") -> Skill:
        """Copy an existing skill (including seed) to a new editable slug."""
        src = self.get(src_slug)
        if src is None:
            raise ValueError(f"원본 스킬을 찾을 수 없음: {src_slug}")
        self.validate_slug(new_slug)
        copy = Skill(
            slug=new_slug,
            name=src.name + name_suffix,
            icon=src.icon,
            kind=src.kind,
            description=src.description,
            system_prompt=src.system_prompt,
            user_prompt_template=src.user_prompt_template,
            tags=tuple(src.tags),
            default_endpoint=src.default_endpoint,
            default_model=src.default_model,
            sample_files=tuple(src.sample_files),
            readonly=False,
        )
        return self.save(copy)


_registry: SkillRegistry | None = None


def get_registry(skills_dir: Path | None = None) -> SkillRegistry:
    """Process-wide singleton. First call sets the directory."""
    global _registry
    if _registry is None:
        if skills_dir is None:
            raise RuntimeError("get_registry()를 처음 호출할 때 skills_dir 인자 필요")
        _registry = SkillRegistry(skills_dir)
    return _registry
