from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Label, ListItem, ListView, Static

from mihomo_ctrl.client import MihomoClient, ProxyGroup, nodes_by_delay

_MIN_GROUP_NAME_WIDTH = 8
_APP_TITLE = "mihomo-ctrl"
_PAN_STEP = 8


def run_tui() -> None:
    MihomoApp().run()


def _cell_len(text: str) -> int:
    return Content(text).cell_length


def _pad_cells(text: str, width: int) -> str:
    extra = width - _cell_len(text)
    if extra <= 0:
        return text
    return f"{text}{' ' * extra}"


def _column_width(texts: list[str], minimum: int = 0) -> int:
    if not texts:
        return minimum
    return max(
        minimum,
        max(_cell_len(text) for text in texts),
    )


def _group_prompt(group: ProxyGroup, type_width: int, name_width: int) -> Content:
    type_col = _pad_cells(f"[{group.proxy_type}]", type_width)
    name_col = _pad_cells(group.name, name_width)
    now_col = group.now if not group.fixed else f"{group.now} *"
    return (
        Content.styled(type_col, "dim")
        + Content(f" {name_col} ")
        + Content.styled(now_col, "dim")
    )


_PINNED_MARK = "⚲"  # 文本字形（非 emoji），用自己的字色渲染


def _nodes_title(group: ProxyGroup) -> str:
    """紧凑：组名放方括号，选中/钉死只用尾标。"""
    mark = _PINNED_MARK if group.fixed else "✓"
    return f"[{group.name}] {group.now} {mark}"


def _node_prompt(name: str, delay: int | None, *, current: bool) -> Content:
    """当前节点用加粗区分，不占列画圆点（标题里也标了 ✓）。"""
    delay_str = f"{delay}ms" if delay is not None else ""
    body = Content.styled(name, "bold") if current else Content.styled(name, "dim")
    if not delay_str:
        return body
    return body + Content.styled(f"  {delay_str}", "dim")


def _keys_hint(bindings: Sequence[BindingType]) -> str:
    parts: list[str] = []
    for binding in bindings:
        if not isinstance(binding, Binding) or not binding.show:
            continue
        key = "⏎" if binding.key == "enter" else binding.key
        parts.append(f"{key} {binding.description}")
    return "  ".join(parts)


class MihomoApp(App[None]):
    """给人用的界面。不要告诉 Agent。"""

    TITLE = _APP_TITLE
    SUB_TITLE = "reading Mihomo…"
    CSS = """
    Screen {
        layout: vertical;
    }
    #topbar {
        height: 1;
        layout: horizontal;
    }
    #title {
        width: 1fr;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    #keys {
        width: auto;
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-wrap: nowrap;
    }
    #body {
        height: 1fr;
    }
    #groups-pane, #nodes-pane {
        height: 1fr;
        border: none;
        padding: 0;
    }
    #groups-pane {
        width: 38.2fr;
    }
    #nodes-pane {
        width: 61.8fr;
        border-left: solid $accent 40%;
    }
    /* 选项用 ListView（子节点）而不是 OptionList：后者自己画行、内容不溢出，
       窄屏时既看不到尾部也滚不动。ListView 的子项设 width: auto，列表就能横向滚。 */
    ListView {
        padding: 0;
        border: none;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 1;
        /* 不设 overflow-x 的话 allow_horizontal_scroll 为 False，
           横向滚轮（SGR 66/67，网页终端左右滑就发这个）会被直接忽略。 */
        overflow-x: auto;
    }
    ListView:focus {
        border: none;
    }
    ListView > ListItem {
        width: auto;
        height: 1;
        padding: 0 1;
        background: transparent;
    }
    ListView > ListItem > Label {
        width: auto;
        text-wrap: nowrap;
    }
    ListView > ListItem.-highlight {
        background: $accent 35%;
    }
    ListView:focus > ListItem.-highlight {
        color: $block-cursor-foreground;
        background: $block-cursor-background;
        text-style: bold;
    }
    .pane-title {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-overflow: ellipsis;
    }
    """
    BINDINGS: ClassVar = [
        Binding("enter", "switch_node", "select", show=True),
        Binding("q", "quit", "quit"),
        Binding("r", "refresh", "refresh"),
        Binding("u", "unpin", "unpin"),
        Binding("left", "scroll_left", "pan", show=False),
        Binding("right", "scroll_right", "pan", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._groups: list[ProxyGroup] = []
        self._delays: dict[str, int] = {}
        self._visible_nodes: list[str] = []
        self._group_index = 0
        self._busy = False
        self._status = self.SUB_TITLE

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(_APP_TITLE, id="title", markup=False)
            yield Static(_keys_hint(self.BINDINGS), id="keys", markup=False)
        with Horizontal(id="body"):
            with Vertical(id="groups-pane"):
                yield Static("Proxy Groups", classes="pane-title", markup=False)
                yield ListView(id="groups")
            with Vertical(id="nodes-pane"):
                yield Static("Options", classes="pane-title", markup=False)
                yield ListView(id="nodes")

    def on_mount(self) -> None:
        self.query_one("#groups", ListView).focus()
        self.action_refresh()

    def action_refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_status("refreshing…")
        self.run_worker(self._reload, exclusive=True, thread=True)

    def action_switch_node(self) -> None:
        if self._busy:
            return
        if getattr(self.focused, "id", None) != "nodes":
            return
        group = self._current_group()
        node = self._current_node()
        if group is None or node is None:
            self._set_status("pick a node first")
            return
        if node == group.now:
            self._set_status(f"{group.name} is already {node}")
            return
        self._busy = True
        self._set_status(f"switching {group.name} → {node}…")
        self.run_worker(
            lambda: self._switch(group.name, node),
            exclusive=True,
            thread=True,
        )

    def action_scroll_left(self) -> None:
        self._pan(-_PAN_STEP)

    def action_scroll_right(self) -> None:
        self._pan(_PAN_STEP)

    def _pan(self, step: int) -> None:
        """←→ 横移当前窗格：窄屏看不到的行尾/标题靠它和拖滚动条看。"""
        focused = self.focused
        if not isinstance(focused, ListView):
            return
        focused.scroll_x = min(max(focused.scroll_x + step, 0), focused.max_scroll_x)

    def action_unpin(self) -> None:
        if self._busy:
            return
        group = self._current_group()
        if group is None:
            self._set_status("pick a proxy group first")
            return
        if not group.fixed:
            self._set_status(f"{group.name} is not pinned")
            return
        self._busy = True
        self._set_status(f"unpinning {group.name}…")
        self.run_worker(
            lambda: self._unpin(group.name),
            exclusive=True,
            thread=True,
        )

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        view = event.list_view
        if view.id == "groups" and view.index is not None:
            self._group_index = view.index
            self._render_nodes()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "nodes":
            self.action_switch_node()

    def _reload(self) -> None:
        try:
            with MihomoClient() as client:
                groups = client.list_groups()
                delays = client.delay_map()
        except Exception as exc:
            self.call_from_thread(self._load_failed, str(exc))
            return
        self.call_from_thread(self._load_ok, groups, delays)

    def _switch(self, group: str, node: str) -> None:
        try:
            with MihomoClient() as client:
                client.switch(group, node)
                groups = client.list_groups()
                delays = client.delay_map()
        except Exception as exc:
            self.call_from_thread(self._load_failed, str(exc))
            return
        self.call_from_thread(
            self._load_ok,
            groups,
            delays,
            f'switched "{group}" → "{node}"'
        )

    def _unpin(self, group: str) -> None:
        try:
            with MihomoClient() as client:
                client.unpin(group)
                groups = client.list_groups()
                delays = client.delay_map()
        except Exception as exc:
            self.call_from_thread(self._load_failed, str(exc))
            return
        self.call_from_thread(
            self._load_ok,
            groups,
            delays,
            f'unpinned "{group}"',
        )

    def _load_ok(
        self,
        groups: list[ProxyGroup],
        delays: dict[str, int],
        status: str | None = None,
    ) -> None:
        self._busy = False
        selected = (
            self._groups[self._group_index].name
            if 0 <= self._group_index < len(self._groups)
            else None
        )
        self._groups = groups
        self._delays = delays
        if selected:
            for index, group in enumerate(groups):
                if group.name == selected:
                    self._group_index = index
                    break
            else:
                self._group_index = 0
        elif groups:
            self._group_index = 0
        self._render_groups()
        self._render_nodes()
        self._set_status(status or f"{len(groups)} groups")

    def _load_failed(self, message: str) -> None:
        self._busy = False
        self._set_status(f"failed: {message}")

    def _render_groups(self) -> None:
        view = self.query_one("#groups", ListView)
        scroll_x = view.scroll_x
        view.clear()
        if not self._groups:
            view.append(ListItem(Label(Content("(no proxy groups)"))))
            return
        type_width = _column_width(
            [f"[{group.proxy_type}]" for group in self._groups],
        )
        name_width = _column_width(
            [group.name for group in self._groups],
            _MIN_GROUP_NAME_WIDTH,
        )
        view.extend(
            ListItem(Label(_group_prompt(group, type_width, name_width)))
            for group in self._groups
        )
        view.index = min(self._group_index, len(self._groups) - 1)
        view.scroll_to(x=scroll_x, animate=False)

    def _render_nodes(self) -> None:
        view = self.query_one("#nodes", ListView)
        scroll_x = view.scroll_x
        view.clear()
        group = self._current_group()
        title = self.query_one("#nodes-pane .pane-title", Static)
        if group is None:
            title.update("Options")
            self._visible_nodes = []
            view.append(ListItem(Label(Content("(pick a proxy group)"))))
            return
        title.update(_nodes_title(group))
        nodes = nodes_by_delay(group.nodes, self._delays)
        self._visible_nodes = nodes
        current_index = 0
        items: list[ListItem] = []
        for index, node in enumerate(nodes):
            delay = self._delays.get(node)
            items.append(
                ListItem(Label(_node_prompt(node, delay, current=node == group.now)))
            )
            if node == group.now:
                current_index = index
        view.extend(items)
        if nodes:
            view.index = current_index
        view.scroll_to(x=scroll_x, animate=False)

    def _current_group(self) -> ProxyGroup | None:
        if 0 <= self._group_index < len(self._groups):
            return self._groups[self._group_index]
        return None

    def _current_node(self) -> str | None:
        index = self.query_one("#nodes", ListView).index
        if index is not None and 0 <= index < len(self._visible_nodes):
            return self._visible_nodes[index]
        return None

    def _set_status(self, text: str) -> None:
        self._status = text
        self.sub_title = text
        self._render_title()

    def _render_title(self) -> None:
        status = self._status
        text = f"{_APP_TITLE}  {status}" if status else _APP_TITLE
        self.query_one("#title", Static).update(text)
