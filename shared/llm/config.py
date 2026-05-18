"""Secret / env loading. Single chokepoint — no other module should touch os.environ."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv, set_key, unset_key
except ImportError:  # python-dotenv missing — fall back to plain env (no write support)
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False

    def set_key(*_args, **_kwargs):
        raise RuntimeError("python-dotenv not installed — `pip install python-dotenv`")

    def unset_key(*_args, **_kwargs):
        raise RuntimeError("python-dotenv not installed — `pip install python-dotenv`")


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_loaded = False


def env_file_path() -> Path:
    """Path to the .env file (may not exist yet)."""
    return _PROJECT_ROOT / ".env"


def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        load_dotenv(env_file_path())
        _loaded = True


def get_secret(key: str, default: str | None = None) -> str | None:
    """Read a value from environment. Never log the result."""
    _ensure_loaded()
    return os.environ.get(key, default)


def mask_secret(value: str | None, visible_tail: int = 4) -> str:
    """Mask a secret for display. Shows prefix + ... + last N chars."""
    if not value:
        return "(unset)"
    if len(value) <= visible_tail + 3:
        return "*" * len(value)
    return f"{value[:3]}...{value[-visible_tail:]}"


# ------------------------------------------------------------
# Mutating helpers — write to .env on disk
# ------------------------------------------------------------

def _ensure_env_file() -> Path:
    """Create .env with 0600 permissions if missing. Returns its path."""
    path = env_file_path()
    if not path.exists():
        path.touch(mode=0o600)
    return path


def _harden_perms(path: Path) -> None:
    """Best-effort: keep .env at owner-only mode (0600). Quietly skip on failure."""
    try:
        path.chmod(0o600)
    except OSError:
        pass


def set_secret(key: str, value: str) -> None:
    """Write `key=value` to .env and update in-process env.

    Creates .env (0600) if missing. After write, re-applies 0600 perms in case
    python-dotenv's atomic-rename clobbered them.
    """
    if not key or not key.replace("_", "").isalnum():
        raise ValueError(f"Invalid env key: {key!r}")
    path = _ensure_env_file()
    set_key(str(path), key, value, quote_mode="always")
    _harden_perms(path)
    os.environ[key] = value


def unset_secret(key: str) -> None:
    """Remove `key` from .env and from in-process env."""
    path = env_file_path()
    if path.exists():
        unset_key(str(path), key)
        _harden_perms(path)
    os.environ.pop(key, None)


def env_file_status() -> dict:
    """Diagnostics about the .env file — for the Settings page."""
    path = env_file_path()
    if not path.exists():
        return {"exists": False, "path": str(path), "mode": None, "world_readable": False}
    mode = path.stat().st_mode & 0o777
    return {
        "exists": True,
        "path": str(path),
        "mode": f"{mode:o}",
        "world_readable": bool(mode & 0o044),
    }
