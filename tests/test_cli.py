from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from mihomo_ctrl.__main__ import (
    _print_groups,
    build_parser,
    cmd_list_proxy_groups,
    cmd_unpin,
    resolve_switch_target,
)
from mihomo_ctrl.client import ProxyGroup


def test_single_arg_switch_uses_default_group() -> None:
    assert resolve_switch_target("美国", None, "PROXY") == ("PROXY", "美国")


def test_two_arg_switch_uses_given_group() -> None:
    assert resolve_switch_target("默认", "美国", "PROXY") == ("默认", "美国")


def test_parser_aliases() -> None:
    parser = build_parser()
    assert parser.parse_args(["lsg", "默认"]).group == "默认"
    assert parser.parse_args(["ls"]).command in {"ls", "list-proxies"}
    args = parser.parse_args(["switch", "默认", "美国"])
    assert args.group_or_node == "默认"
    assert args.node == "美国"
    assert parser.parse_args(["clear-cache"]).path is None
    assert parser.parse_args(["tui"]).command == "tui"
    args = parser.parse_args(["unpin", "自动选择"])
    assert args.command == "unpin"
    assert args.group == "自动选择"


def test_version_option_prints_package_version(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert version("mihomo-ctrl") in out
    assert "unknown" not in out


def test_lsg_group_prints_nodes_by_delay(capsys) -> None:
    group = ProxyGroup("美国", "Selector", "slow", ("slow", "none", "fast"))
    client = _fake_client(group)
    client.delay_map.return_value = {"slow": 200, "fast": 20}
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_list_proxy_groups(SimpleNamespace(group="美国"))
    options = capsys.readouterr().out.split("Options:", 1)[1]
    assert options.index("fast") < options.index("slow") < options.index("none")


def test_print_groups_marks_pinned(capsys) -> None:
    _print_groups(
        [
            ProxyGroup("默认", "Selector", "美国", ("美国",)),
            ProxyGroup("自动选择", "URLTest", "HK-01", ("HK-01",), "HK-01"),
        ]
    )
    out = capsys.readouterr().out
    assert "默认" in out
    assert "-> 美国" in out
    assert "自动选择" in out
    assert "HK-01 *" in out


def _fake_client(group: ProxyGroup) -> MagicMock:
    client = MagicMock()
    client.get_group.return_value = group
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    return client


def test_cmd_unpin_skips_when_not_pinned(capsys) -> None:
    group = ProxyGroup("自动选择", "URLTest", "HK-01", ("HK-01",))
    client = _fake_client(group)
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_unpin(SimpleNamespace(group="自动选择"))
    client.unpin.assert_not_called()
    assert "not pinned" in capsys.readouterr().out


def test_cmd_unpin_deletes_when_pinned(capsys) -> None:
    group = ProxyGroup("自动选择", "URLTest", "HK-01", ("HK-01",), "HK-01")
    client = _fake_client(group)
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_unpin(SimpleNamespace(group="自动选择"))
    client.unpin.assert_called_once_with("自动选择")
    assert "Unpinned" in capsys.readouterr().out
