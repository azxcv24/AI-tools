"""Path-safe file manager. Scoped to a single root directory."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO


@dataclass
class FileInfo:
    name: str
    path: Path
    size: int
    modified: datetime


class FileManager:
    """Manages files inside a single root dir. Rejects path traversal.

    Only single-segment filenames are accepted (no `/` or `\\`). The resolved
    path is checked against the root to prevent symlink escapes.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe(self, name: str) -> Path:
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"Unsafe filename: {name!r}")
        p = (self.root / name).resolve()
        try:
            p.relative_to(self.root)
        except ValueError as e:
            raise ValueError(f"Path escapes root: {name!r}") from e
        return p

    def save(self, name: str, data: bytes) -> FileInfo:
        p = self._safe(name)
        p.write_bytes(data)
        return self.info(name)

    def save_stream(self, name: str, stream: BinaryIO) -> FileInfo:
        p = self._safe(name)
        with p.open("wb") as f:
            shutil.copyfileobj(stream, f)
        return self.info(name)

    def read(self, name: str) -> bytes:
        return self._safe(name).read_bytes()

    def delete(self, name: str) -> None:
        self._safe(name).unlink(missing_ok=True)

    def exists(self, name: str) -> bool:
        return self._safe(name).is_file()

    def list(self) -> list[FileInfo]:
        return [
            self._info(p)
            for p in sorted(self.root.iterdir(), key=lambda x: x.name)
            if p.is_file()
        ]

    def info(self, name: str) -> FileInfo:
        return self._info(self._safe(name))

    @staticmethod
    def _info(p: Path) -> FileInfo:
        st = p.stat()
        return FileInfo(
            name=p.name,
            path=p,
            size=st.st_size,
            modified=datetime.fromtimestamp(st.st_mtime),
        )
