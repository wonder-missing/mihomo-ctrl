import asyncio
from types import SimpleNamespace

from textual.widgets import Footer, Static

from mihomo_ctrl.client import ProxyGroup
from mihomo_ctrl.tui import (
    _MIN_GROUP_NAME_WIDTH,
    MihomoApp,
    _cell_len,
    _column_width,
    _group_prompt,
    _keys_hint,
    _node_prompt,
    _nodes_title,
    _pad_cells,
)


def _group(name: str, proxy_type: str, now: str) -> ProxyGroup:
    return ProxyGroup(name=name, proxy_type=proxy_type, now=now, nodes=())


def test_pad_cells_aligns_cjk() -> None:
    padded = _pad_cells("默认", 8)
    assert _cell_len(padded) == 8
    assert padded.startswith("默认")


def test_column_width_uses_minimum() -> None:
    assert _column_width(["a", "bb"], _MIN_GROUP_NAME_WIDTH) == _MIN_GROUP_NAME_WIDTH


def test_group_prompt_aligns_now_and_drops_arrow() -> None:
    groups = [
        _group("默认", "Selector", "自动选择"),
        _group("美国", "URLTest", "US-01"),
    ]
    type_width = _column_width([f"[{group.proxy_type}]" for group in groups])
    name_width = _column_width(
        [group.name for group in groups],
        _MIN_GROUP_NAME_WIDTH,
    )
    plains = [
        _group_prompt(group, type_width, name_width).plain for group in groups
    ]
    offsets = [
        _cell_len(plain[: plain.rindex(group.now)])
        for plain, group in zip(plains, groups)
    ]
    assert offsets[0] == offsets[1]
    assert all("→" not in plain for plain in plains)


def test_group_prompt_keeps_long_now() -> None:
    now = "A" * 40
    plain = _group_prompt(_group("新加坡", "Selector", now), 10, 8).plain
    assert now in plain
    assert "…" not in plain


def test_group_prompt_marks_pinned() -> None:
    group = ProxyGroup(
        name="自动选择",
        proxy_type="URLTest",
        now="HK-01",
        nodes=(),
        fixed="HK-01",
    )
    plain = _group_prompt(group, 10, 8).plain
    assert plain.endswith("HK-01 *")


def test_nodes_title_uses_pinned_wording() -> None:
    free = _group("美国", "Selector", "US-01")
    pinned = ProxyGroup(
        name="自动选择",
        proxy_type="URLTest",
        now="HK-01",
        nodes=(),
        fixed="HK-01",
    )
    assert "当前 US-01" in _nodes_title(free)
    assert "钉死 HK-01" in _nodes_title(pinned)


def test_keys_hint_follows_bindings() -> None:
    hint = _keys_hint(MihomoApp.BINDINGS)
    assert hint.startswith("⏎ 选择")
    assert "q 退出" in hint
    assert "r 刷新" in hint
    assert "u 消钉" in hint


def test_format_title_separates_with_spaces() -> None:
    content = MihomoApp().format_title("mihomo-ctrl", "正在刷新…")
    assert "—" not in content.plain
    assert content.plain == "mihomo-ctrl  正在刷新…"


def test_node_prompt_marks_only_current() -> None:
    current = _node_prompt("HK-01", 42, current=True)
    other = _node_prompt("US-01", 88, current=False)
    assert current.plain.startswith("● ")
    assert other.plain.startswith("  ")
    assert "42ms" in current.plain
    assert "88ms" in other.plain


def test_nodes_selected_triggers_switch() -> None:
    app = MihomoApp()
    called: list[bool] = []
    app.action_switch_node = lambda: called.append(True)
    event = SimpleNamespace(option_list=SimpleNamespace(id="nodes"))
    app.on_option_list_option_selected(event)  # type: ignore[arg-type]
    assert called == [True]


def test_groups_selected_does_not_switch() -> None:
    app = MihomoApp()
    called: list[bool] = []
    app.action_switch_node = lambda: called.append(True)
    event = SimpleNamespace(option_list=SimpleNamespace(id="groups"))
    app.on_option_list_option_selected(event)  # type: ignore[arg-type]
    assert called == []


def test_enter_on_groups_does_not_claim_already_selected() -> None:
    group = ProxyGroup("默认", "Selector", "美国", ("美国", "香港"))

    class Preview(MihomoApp):
        def on_mount(self) -> None:
            self.query_one("#groups").focus()
            self._load_ok([group], {}, "ok")

    async def check() -> None:
        app = Preview()
        async with app.run_test(size=(100, 20)) as pilot:
            assert app.focused is not None
            assert app.focused.id == "groups"
            await pilot.press("enter")
            assert app._busy is False
            assert "已经是" not in app.sub_title

    asyncio.run(check())


def test_unpin_without_fixed_does_not_run() -> None:
    app = MihomoApp()
    app._groups = [_group("自动选择", "URLTest", "HK-01")]
    app._group_index = 0
    workers: list[object] = []
    app.run_worker = lambda *args, **kwargs: workers.append(args)
    statuses: list[str] = []
    app._set_status = lambda text: statuses.append(text)
    app.action_unpin()
    assert app._busy is False
    assert workers == []
    assert statuses == ["自动选择 没有钉死"]


def test_unpin_with_fixed_starts_worker() -> None:
    app = MihomoApp()
    app._groups = [
        ProxyGroup(
            name="自动选择",
            proxy_type="URLTest",
            now="HK-01",
            nodes=(),
            fixed="HK-01",
        )
    ]
    app._group_index = 0
    workers: list[object] = []
    app.run_worker = lambda *args, **kwargs: workers.append(args)
    app._set_status = lambda _text: None
    app.action_unpin()
    assert app._busy is True
    assert workers


def test_refresh_sets_busy_before_worker() -> None:
    app = MihomoApp()
    app._set_status = lambda _text: None
    workers: list[object] = []
    app.run_worker = lambda *args, **kwargs: workers.append(args)
    app.action_refresh()
    assert app._busy is True
    assert workers


def test_layout_clips_long_now_and_keeps_title() -> None:
    now = "超长节点名称-" + "X" * 40
    groups = [
        ProxyGroup("默认", "Selector", now, (now, "备用")),
    ]

    class Preview(MihomoApp):
        def on_mount(self) -> None:
            self.query_one("#groups").focus()
            self._load_ok(groups, {}, "ok")

    async def check() -> None:
        app = Preview()
        async with app.run_test(size=(100, 20)):
            left = app.query_one("#groups-pane")
            right = app.query_one("#nodes-pane")
            ratio = left.size.width / right.size.width
            assert 0.55 < ratio < 0.8
            glist = app.query_one("#groups")
            assert glist._heights[0] == 1
            title = app.query_one("#nodes-pane .pane-title", Static)
            assert isinstance(title.content, str)
            assert f"当前 {now}" in title.content
            keys = app.query_one("#header-keys", Static)
            assert "选择" in str(keys.content)
            assert list(app.query(Footer)) == []
            header_title = app.query_one("HeaderTitle")
            assert header_title.styles.content_align_horizontal == "left"
            icon = app.query_one("HeaderIcon")
            assert icon.size.width <= 3
            assert header_title.region.right <= keys.region.x

    asyncio.run(check())


def test_header_long_status_does_not_cover_keys() -> None:
    class Preview(MihomoApp):
        def on_mount(self) -> None:
            self.query_one("#groups").focus()
            self._set_status("已切换 " + "很长的名字" * 20)

    async def check() -> None:
        app = Preview()
        async with app.run_test(size=(80, 16)):
            title = app.query_one("HeaderTitle")
            keys = app.query_one("#header-keys")
            assert title.region.right <= keys.region.x
            assert "选择" in str(keys.content)

    asyncio.run(check())
