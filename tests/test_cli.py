from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from mihomo_ctrl.__main__ import (
    _print_groups,
    build_parser,
    cmd_list_proxy_groups,
    cmd_logs,
    cmd_reload,
    cmd_switch,
    cmd_unpin,
    resolve_switch_target,
)
from mihomo_ctrl.client import ProxyGroup
from mihomo_ctrl.errors import MihomoError


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
    assert args.force is False
    assert parser.parse_args(["switch", "默认", "美国", "--force"]).force is True
    assert parser.parse_args(["clear-cache"]).path is None
    assert parser.parse_args(["tui"]).command == "tui"
    args = parser.parse_args(["unpin", "自动选择"])
    assert args.command == "unpin"
    assert args.group == "自动选择"
    logs = parser.parse_args(["logs"])
    assert logs.lines == 10
    assert logs.follow is False
    assert logs.level is None
    followed = parser.parse_args(["logs", "-n", "3", "-f", "--level", "warning"])
    assert followed.lines == 3
    assert followed.follow is True
    assert followed.level == "warning"
    assert parser.parse_args(["reload"]).path is None
    assert parser.parse_args(["reload", "/tmp/c.yaml"]).path == "/tmp/c.yaml"


def test_version_option_prints_package_version(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert version("mihomo-ctrl") in out
    assert "unknown" not in out


def test_lsg_leaf_selector_prints_nodes_by_delay(capsys) -> None:
    group = ProxyGroup("美国", "Selector", "slow", ("slow", "none", "fast"))
    client = _fake_client(group)
    client.delay_map.return_value = {"slow": 200, "fast": 20}
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_list_proxy_groups(SimpleNamespace(group="美国"))
    out = capsys.readouterr().out
    assert "Order: delay" in out
    options = out.split("Options:", 1)[1]
    assert options.index("fast") < options.index("slow") < options.index("none")


def test_lsg_fallback_prints_member_order(capsys) -> None:
    group = ProxyGroup("稳定", "Fallback", "first", ("first", "second", "fast"))
    client = _fake_client(group)
    client.delay_map.return_value = {"fast": 10, "first": 400}
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_list_proxy_groups(SimpleNamespace(group="稳定"))
    options = capsys.readouterr().out.split("Options:", 1)[1]
    assert options.index("first") < options.index("second") < options.index("fast")
    assert "(400ms)" in options
    assert "(10ms)" in options


def test_lsg_selector_of_groups_prints_member_order(capsys) -> None:
    group = ProxyGroup("其他", "Selector", "稳定", ("稳定", "香港", "自动选择"))
    client = _fake_client(group)
    client.proxies.return_value = {
        "其他": {"type": "Selector", "all": ["稳定", "香港", "自动选择"]},
        "稳定": {"type": "Fallback", "all": ["first"]},
        "香港": {"type": "Selector", "all": ["HK-01"]},
        "自动选择": {"type": "URLTest", "all": ["SG-01"]},
    }
    client.delay_map.return_value = {"香港": 10, "自动选择": 20}
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_list_proxy_groups(SimpleNamespace(group="其他"))
    out = capsys.readouterr().out
    assert "Order: member" in out
    options = out.split("Options:", 1)[1]
    assert options.index("稳定") < options.index("香港") < options.index("自动选择")


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
    client.proxies.return_value = {}
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
    pinned = ProxyGroup("自动选择", "URLTest", "HK-01", ("HK-01",), "HK-01")
    freed = ProxyGroup("自动选择", "URLTest", "HK-01", ("HK-01",))
    client = _fake_client(pinned)
    client.get_group.side_effect = [pinned, freed]
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_unpin(SimpleNamespace(group="自动选择"))
    client.unpin.assert_called_once_with("自动选择")
    assert "Unpinned" in capsys.readouterr().out


def test_parser_rejects_non_positive_line_count() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["logs", "-n", "0"])


def test_cmd_logs_limits_when_not_following(capsys) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    client.read_logs.return_value = iter(["10:00:01 [info] one"])
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_logs(SimpleNamespace(follow=False, lines=4, level=None))
    client.read_logs.assert_called_once_with(level=None, limit=4)
    assert "one" in capsys.readouterr().out


def test_cmd_logs_follow_does_not_cap() -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    client.read_logs.return_value = iter(())
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_logs(SimpleNamespace(follow=True, lines=4, level="debug"))
    client.read_logs.assert_called_once_with(level="debug", limit=None)


def test_cmd_logs_keyboard_interrupt_is_quiet(capsys) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    client.read_logs.side_effect = KeyboardInterrupt
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_logs(SimpleNamespace(follow=True, lines=10, level=None))
    assert capsys.readouterr().out == ""


def test_cmd_reload_rejects_relative_path() -> None:
    with pytest.raises(MihomoError, match="绝对路径"):
        cmd_reload(SimpleNamespace(path="config.yaml"))


def test_cmd_reload_expands_home_and_prints(capsys) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_reload(SimpleNamespace(path="~/mihomo/config.yaml"))
    path = client.reload.call_args.args[0]
    assert path.startswith("/")
    assert path.endswith("/mihomo/config.yaml")
    assert f"Reloaded config: {path}" in capsys.readouterr().out


def test_cmd_reload_empty_uses_startup_config(capsys) -> None:
    client = MagicMock()
    client.__enter__.return_value = client
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_reload(SimpleNamespace(path=None))
    client.reload.assert_called_once_with("")
    assert "Reloaded startup config" in capsys.readouterr().out


def test_cmd_unpin_reports_when_still_pinned() -> None:
    pinned = ProxyGroup("自动选择", "URLTest", "HK-01", ("HK-01",), "HK-01")
    client = _fake_client(pinned)
    client.get_group.side_effect = [pinned, pinned]
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        with pytest.raises(MihomoError, match="did not stick"):
            cmd_unpin(SimpleNamespace(group="自动选择"))


def _switch_client(before: ProxyGroup, after: ProxyGroup) -> MagicMock:
    client = _fake_client(before)
    client.get_group.side_effect = [before, after]
    client.proxy_index.return_value = {
        "默认": {"type": "Selector", "all": ["自动选择", "美国", "直连"]},
        "自动选择": {"type": "URLTest", "all": ["HK-01"]},
        "美国": {"type": "Selector", "all": ["US-01"]},
        "直连": {"type": "Direct"},
        "US-01": {"type": "Shadowsocks"},
    }
    return client


def _switch_args(node: str, force: bool = False) -> SimpleNamespace:
    return SimpleNamespace(group_or_node="默认", node=node, force=force)


def test_cmd_switch_refuses_cross_level(capsys) -> None:
    before = ProxyGroup("默认", "Selector", "自动选择", ("自动选择", "美国", "直连"))
    client = _switch_client(before, before)
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        with pytest.raises(MihomoError, match="cross-level"):
            cmd_switch(_switch_args("US-01"))
    client.switch.assert_not_called()


def test_cmd_switch_force_skips_cross_level_guard(capsys) -> None:
    before = ProxyGroup("默认", "Selector", "自动选择", ("自动选择", "美国", "直连"))
    after = ProxyGroup("默认", "Selector", "US-01", before.nodes)
    client = _switch_client(before, after)
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        cmd_switch(_switch_args("US-01", force=True))
    client.switch.assert_called_once_with("默认", "US-01")
    assert "Switched" in capsys.readouterr().out


def test_cmd_switch_reports_when_target_does_not_stick() -> None:
    before = ProxyGroup("默认", "Selector", "自动选择", ("自动选择", "美国", "直连"))
    client = _switch_client(before, before)
    with patch("mihomo_ctrl.__main__.MihomoClient", return_value=client):
        with pytest.raises(MihomoError, match="did not stick"):
            cmd_switch(_switch_args("美国"))
