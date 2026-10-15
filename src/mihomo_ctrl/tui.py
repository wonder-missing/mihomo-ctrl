from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Header, OptionList, Static
from textual.widgets._header import HeaderIcon, HeaderTitle
from textual.widgets.option_list import Option

from mihomo_ctrl.client import MihomoClient, ProxyGroup, nodes_by_delay

_MIN_GROUP_NAME_WIDTH = 8


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


def _nodes_title(group: ProxyGroup) -> str:
    state = "钉死" if group.fixed else "当前"
    return f"{group.name}  ·  {group.proxy_type}  ·  {state} {group.now}"


def _node_prompt(name: str, delay: int | None, *, current: bool) -> Content:
    delay_str = f"{delay}ms" if delay is not None else ""
    marker = "● " if current else "  "
    label = f"{marker}{name}"
    body = Content.styled(label, "bold") if current else Content.styled(label, "dim")
    if not delay_str:
        return body
    return body + Content.styled(f"  {delay_str}", "dim")


def _keys_hint(bindings: Sequence[BindingType]) -> str:
    parts: list[str] = []
    for binding in bindings:
        if not isinstance(binding, Binding):
            continue
        key = "⏎" if binding.key == "enter" else binding.key
        parts.append(f"{key} {binding.description}")
    return "  ".join(parts)


class AppHeader(Header):
    def compose(self) -> ComposeResult:
        yield HeaderIcon().data_bind(Header.icon)
        yield HeaderTitle()
        yield Static(_keys_hint(MihomoApp.BINDINGS), id="header-keys")

    def _on_click(self) -> None:
        return


class MihomoApp(App[None]):
    """给人用的界面。不要告诉 Agent。"""

    TITLE = "mihomo-ctrl"
    SUB_TITLE = "正在读取 Mihomo…"
    CSS = """
    Screen {
        layout: vertical;
    }
    Header {
        layout: horizontal;
    }
    Header.-tall {
        height: 1;
    }
    HeaderIcon {
        dock: none;
        width: 3;
        padding: 0 1;
        content-align: center middle;
    }
    HeaderTitle {
        width: 1fr;
        content-align: left middle;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    #header-keys {
        dock: none;
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
        width: 4fr;
    }
    #nodes-pane {
        width: 6fr;
        border-left: solid $accent 40%;
    }
    OptionList {
        padding: 0;
        border: none;
        scrollbar-size-vertical: 1;
        text-wrap: nowrap;
        text-overflow: clip;
    }
    OptionList:focus {
        border: none;
    }
    #nodes-pane OptionList > .option-list--option-highlighted {
        background: $accent 35%;
    }
    #nodes-pane OptionList:focus > .option-list--option-highlighted {
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
        Binding("enter", "switch_node", "选择", show=True),
        Binding("q", "quit", "退出"),
        Binding("r", "refresh", "刷新"),
        Binding("u", "unpin", "消钉"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._groups: list[ProxyGroup] = []
        self._delays: dict[str, int] = {}
        self._visible_nodes: list[str] = []
        self._group_index = 0
        self._busy = False

    def compose(self) -> ComposeResult:
        yield AppHeader(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="groups-pane"):
                yield Static("代理组  ↑↓", classes="pane-title")
                yield OptionList(id="groups")
            with Vertical(id="nodes-pane"):
                yield Static("选项  Tab · Enter 选择", classes="pane-title")
                yield OptionList(id="nodes")

    def format_title(self, title: str, sub_title: str) -> Content:
        if not sub_title:
            return Content(title)
        return Content.assemble(
            Content(title),
            "  ",
            Content(sub_title).stylize("dim"),
        )

    def on_mount(self) -> None:
        self.query_one("#groups", OptionList).focus()
        self.action_refresh()

    def action_refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_status("正在刷新…")
        self.run_worker(self._reload, exclusive=True, thread=True)

    def action_switch_node(self) -> None:
        if self._busy:
            return
        if getattr(self.focused, "id", None) != "nodes":
            return
        group = self._current_group()
        node = self._current_node()
        if group is None or node is None:
            self._set_status("先选一个节点")
            return
        if node == group.now:
            self._set_status(f"{group.name} 已经是 {node}")
            return
        self._busy = True
        self._set_status(f"切换 {group.name} → {node} …")
        self.run_worker(
            lambda: self._switch(group.name, node),
            exclusive=True,
            thread=True,
        )

    def action_unpin(self) -> None:
        if self._busy:
            return
        group = self._current_group()
        if group is None:
            self._set_status("先选一个代理组")
            return
        if not group.fixed:
            self._set_status(f"{group.name} 没有钉死")
            return
        self._busy = True
        self._set_status(f"取消 {group.name} 的钉死…")
        self.run_worker(
            lambda: self._unpin(group.name),
            exclusive=True,
            thread=True,
        )

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option_list.id == "groups":
            self._group_index = event.option_index
            self._render_nodes()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "nodes":
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
            f'已切换 "{group}" → "{node}"',
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
            f'已取消 "{group}" 的钉死',
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
        self._set_status(status or f"{len(groups)} 个代理组")

    def _load_failed(self, message: str) -> None:
        self._busy = False
        self._set_status(f"失败：{message}")

    def _render_groups(self) -> None:
        widget = self.query_one("#groups", OptionList)
        widget.clear_options()
        if not self._groups:
            widget.add_option(Option("(没有代理组)"))
            return
        type_width = _column_width(
            [f"[{group.proxy_type}]" for group in self._groups],
        )
        name_width = _column_width(
            [group.name for group in self._groups],
            _MIN_GROUP_NAME_WIDTH,
        )
        for group in self._groups:
            widget.add_option(
                Option(
                    _group_prompt(group, type_width, name_width),
                )
            )
        widget.highlighted = min(self._group_index, len(self._groups) - 1)

    def _render_nodes(self) -> None:
        widget = self.query_one("#nodes", OptionList)
        widget.clear_options()
        group = self._current_group()
        title = self.query_one("#nodes-pane .pane-title", Static)
        if group is None:
            title.update("选项")
            self._visible_nodes = []
            widget.add_option(Option("(先选代理组)"))
            return
        title.update(_nodes_title(group))
        nodes = nodes_by_delay(group.nodes, self._delays)
        self._visible_nodes = nodes
        current_index = 0
        for index, node in enumerate(nodes):
            delay = self._delays.get(node)
            widget.add_option(
                Option(
                    _node_prompt(node, delay, current=node == group.now),
                )
            )
            if node == group.now:
                current_index = index
        if nodes:
            widget.highlighted = current_index

    def _current_group(self) -> ProxyGroup | None:
        if 0 <= self._group_index < len(self._groups):
            return self._groups[self._group_index]
        return None

    def _current_node(self) -> str | None:
        widget = self.query_one("#nodes", OptionList)
        index = widget.highlighted
        if index is None:
            return None
        if 0 <= index < len(self._visible_nodes):
            return self._visible_nodes[index]
        return None

    def _set_status(self, text: str) -> None:
        self.sub_title = text
