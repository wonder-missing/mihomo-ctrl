from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from mihomo_ctrl.errors import MihomoError

logger = logging.getLogger(__name__)

CACHE_NAME = "cache.db"
_CORE_NAMES = frozenset({"mihomo", "clash", "clash-meta"})

DEFAULT_DIRS = (
    "~/.config/mihomo",
    "~/.config/clash",
    "~/Library/Application Support/com.metacubex.mihomo",
)


def cache_paths_from_ps(output: str) -> list[Path]:
    """从 `ps -ef` 输出里找出 `-d/--dir` 对应的 cache.db 路径。"""
    paths: list[Path] = []
    for parts in _core_ps_rows(output):
        for index, part in enumerate(parts):
            if part in ("-d", "--dir") and index + 1 < len(parts):
                paths.append(Path(parts[index + 1]) / CACHE_NAME)
    return paths


def cache_path_from_lsof(output: str) -> Path | None:
    for line in output.splitlines():
        if line.startswith("n"):
            return Path(line[1:]) / CACHE_NAME
    return None


def detect_cache_path() -> Path:
    candidates: list[Path] = []
    candidates.extend(_live_process_candidates())
    candidates.extend(Path(raw).expanduser() / CACHE_NAME for raw in DEFAULT_DIRS)
    return _first_existing(candidates) or Path("~/.config/mihomo/cache.db").expanduser()


def reset_cache(path: Path) -> bool:
    """删除 cache.db。有文件被删掉就返回 True。"""
    if path.name != CACHE_NAME:
        raise MihomoError(
            f"Security check failed: Target must be a '{CACHE_NAME}' file, got: {path}"
        )
    try:
        path.unlink()
    except FileNotFoundError:
        logger.info("cache file already absent: %s", path)
        return False
    except OSError as exc:
        logger.error("failed to remove cache file %s: %s", path, exc)
        raise MihomoError(f"Failed to remove cache file: {exc}") from exc
    logger.info("removed cache file: %s", path)
    return True


def _live_process_candidates() -> list[Path]:
    candidates: list[Path] = []
    try:
        output = subprocess.check_output(["ps", "-ef"], text=True, errors="ignore")
    except OSError as exc:
        logger.debug("ps failed: %s", exc)
        return candidates

    candidates.extend(cache_paths_from_ps(output))

    for parts in _core_ps_rows(output):
        lsof_path = _cwd_cache_path(parts[1])
        if lsof_path is not None:
            candidates.append(lsof_path)
    return candidates


def _core_ps_rows(output: str) -> list[list[str]]:
    self_pid = str(os.getpid())
    rows: list[list[str]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] == self_pid:
            continue
        names = [Path(part).name for part in parts]
        if "grep" in names:
            continue
        if any(name in _CORE_NAMES for name in names):
            rows.append(parts)
    return rows


def _cwd_cache_path(pid: str) -> Path | None:
    try:
        output = subprocess.check_output(
            ["lsof", "-a", "-d", "cwd", "-p", pid, "-Fn"],
            text=True,
            errors="ignore",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.debug("lsof pid=%s failed: %s", pid, exc)
        return None
    return cache_path_from_lsof(output)


def _first_existing(paths: list[Path]) -> Path | None:
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return None
