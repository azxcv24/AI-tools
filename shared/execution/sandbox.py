"""Subprocess-based sandbox for running LLM-generated code.

Defense-in-depth, not bulletproof:
- Runs in a fresh subprocess (parent process is safe).
- Hard timeout via subprocess.run.
- POSIX rlimits: memory (RLIMIT_AS), CPU, file descriptors, core dumps.
- Stripped environment — no proxy, no user secrets leaked.
- Working dir is a fresh temp dir; only the listed input files are seeded.
- Any new files in the temp dir post-run are collected as outputs.

Assumes the host is your own machine (the user generates+runs code locally).
NOT a replacement for container/VM isolation if exposing to untrusted users.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import resource  # POSIX-only
    _HAVE_RESOURCE = True
except ImportError:  # pragma: no cover
    _HAVE_RESOURCE = False


@dataclass
class SandboxResult:
    ok: bool
    elapsed: float
    stdout: str = ""
    stderr: str = ""
    return_code: int | None = None
    outputs: dict[str, bytes] = field(default_factory=dict)
    error: str | None = None  # high-level failure reason (timeout, exception)


def _make_preexec(memory_mb: int, cpu_seconds: int):
    """Build a preexec_fn that sets resource limits in the child process."""
    if not _HAVE_RESOURCE:
        return None

    def _apply() -> None:
        mem_bytes = memory_mb * 1024 * 1024
        # Address space cap (virtual memory)
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        # CPU time cap — soft, then SIGKILL hard
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
        # No core dumps
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        # FD cap
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

    return _apply


def run_pandas_code(
    code: str,
    inputs: dict[str, bytes],
    timeout_seconds: int = 60,
    memory_limit_mb: int = 1024,
) -> SandboxResult:
    """Run `code` in an isolated subprocess. Inputs are written into the
    working dir before execution. New files appearing in the working dir
    after execution are collected as `outputs`.
    """
    with tempfile.TemporaryDirectory(prefix="lstudio_sbx_") as tmp:
        tmp_path = Path(tmp)

        # 1. seed input files
        for name, data in inputs.items():
            safe = Path(name).name  # strip any path components
            (tmp_path / safe).write_bytes(data)

        # 2. write user code
        code_file = tmp_path / "_user_code.py"
        code_file.write_text(code, encoding="utf-8")

        # 3. snapshot for diff
        before = {p.name for p in tmp_path.iterdir() if p.is_file()}

        # 4. minimal env — preserve PYTHONPATH so user-site packages are visible
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        }
        # Preserve site-packages discovery (user-installed pandas etc.)
        for k in ("PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX"):
            if k in os.environ:
                env[k] = os.environ[k]

        t0 = time.time()
        try:
            cp = subprocess.run(
                [sys.executable, "_user_code.py"],
                cwd=str(tmp_path),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                preexec_fn=_make_preexec(memory_limit_mb, timeout_seconds),
            )
        except subprocess.TimeoutExpired as e:
            return SandboxResult(
                ok=False,
                elapsed=time.time() - t0,
                stdout=(e.stdout or b"").decode("utf-8", "replace"),
                stderr=(e.stderr or b"").decode("utf-8", "replace"),
                error=f"timeout after {timeout_seconds}s",
            )
        except Exception as e:
            return SandboxResult(
                ok=False,
                elapsed=time.time() - t0,
                error=f"{type(e).__name__}: {e}",
            )

        elapsed = time.time() - t0

        # 5. collect new files as outputs
        outputs: dict[str, bytes] = {}
        for p in sorted(tmp_path.iterdir()):
            if not p.is_file() or p.name in before or p.name == "_user_code.py":
                continue
            try:
                outputs[p.name] = p.read_bytes()
            except OSError:
                pass

        return SandboxResult(
            ok=cp.returncode == 0,
            elapsed=elapsed,
            stdout=cp.stdout.decode("utf-8", "replace"),
            stderr=cp.stderr.decode("utf-8", "replace"),
            return_code=cp.returncode,
            outputs=outputs,
        )
