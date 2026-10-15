from pathlib import Path

import pytest

from mihomo_ctrl.cache import (
    cache_path_from_lsof,
    cache_paths_from_ps,
    reset_cache,
)
from mihomo_ctrl.errors import MihomoError


def test_ps_extracts_dir_flag() -> None:
    output = """
root  1  0  0  0  ??  Ss  0:00.01 /sbin/launchd
user  42 1  0  0  ??  S   0:01.00 /opt/homebrew/bin/mihomo -d /tmp/mihomo-data
user  43 1  0  0  ??  S   0:00.00 grep mihomo
"""
    paths = cache_paths_from_ps(output)
    assert paths == [Path("/tmp/mihomo-data/cache.db")]


def test_ps_ignores_unrelated_and_grep() -> None:
    output = "user  9  1  0 ?? S 0:00.00 grep clash\n"
    assert cache_paths_from_ps(output) == []


def test_ps_ignores_ctrl_and_python_module() -> None:
    output = """
user  10 1  0  0  ??  S   0:00.00 /Users/clawdy/bin/mihomo-ctrl reset
user  11 1  0  0  ??  S   0:00.00 python -m mihomo_ctrl reset
user  12 1  0  0  ??  S   0:00.00 uv run mihomo-ctrl lsg
user  13 1  0  0  ??  S   0:00.00 /opt/homebrew/bin/mihomo -d /tmp/real
"""
    assert cache_paths_from_ps(output) == [Path("/tmp/real/cache.db")]


def test_ps_accepts_clash_meta() -> None:
    output = (
        "user  8 1  0  0  ??  S   0:00.00 /usr/local/bin/clash-meta --dir /etc/clash\n"
    )
    assert cache_paths_from_ps(output) == [Path("/etc/clash/cache.db")]


def test_ps_skips_current_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mihomo_ctrl.cache.os.getpid", lambda: 42)
    output = "user  42 1  0  0  ??  S   0:01.00 /opt/homebrew/bin/mihomo -d /tmp/self\n"
    assert cache_paths_from_ps(output) == []


def test_default_dirs_do_not_include_cwd() -> None:
    from mihomo_ctrl.cache import DEFAULT_DIRS

    assert "." not in DEFAULT_DIRS


def test_lsof_cwd_line() -> None:
    output = "p42\nfcwd\nn/Users/clawdy/.config/mihomo\n"
    assert cache_path_from_lsof(output) == Path("/Users/clawdy/.config/mihomo/cache.db")


def test_reset_rejects_non_cache_db(tmp_path: Path) -> None:
    other = tmp_path / "config.yaml"
    other.write_text("x")
    with pytest.raises(MihomoError, match="Security check failed"):
        reset_cache(other)


def test_reset_removes_existing_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache.db"
    cache.write_bytes(b"db")
    assert reset_cache(cache) is True
    assert not cache.exists()


def test_reset_missing_cache_is_clean(tmp_path: Path) -> None:
    cache = tmp_path / "cache.db"
    assert reset_cache(cache) is False
