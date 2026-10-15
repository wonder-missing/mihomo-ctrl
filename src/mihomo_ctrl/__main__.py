"""Mihomo CLI 入口。--help 输出应能充当一份 SKILL。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mihomo_ctrl.cache import detect_cache_path, reset_cache
from mihomo_ctrl.client import MihomoClient, ProxyGroup, nodes_by_delay
from mihomo_ctrl.config import settings
from mihomo_ctrl.errors import MihomoAPIError, MihomoError

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)


def resolve_switch_target(
    group_or_node: str, node: str | None, default_group: str
) -> tuple[str, str]:
    if node is None:
        return default_group, group_or_node
    return group_or_node, node


def cmd_list_proxy_groups(args: argparse.Namespace) -> None:
    with MihomoClient() as client:
        if not args.group:
            _print_groups(client.list_groups())
            return

        group = client.get_group(args.group)
        delays = client.delay_map()
        print(f"=== Proxy Group: {group.name} ===")
        print(f"Type: {group.proxy_type}")
        print(f"Current: {group.now}")
        if group.fixed:
            print(f"Pinned: {group.fixed}")
        print("Options:")
        for node in nodes_by_delay(group.nodes, delays):
            delay = delays.get(node)
            delay_str = f" ({delay}ms)" if delay is not None else ""
            marker = "[*]" if node == group.now else "[ ]"
            print(f"  {marker} {node}{delay_str}")


def cmd_list_proxies(_args: argparse.Namespace) -> None:
    with MihomoClient() as client:
        items = client.leaf_proxies()

    print("=== Mihomo All Proxies (Sorted by Delay) ===")
    if not items:
        print("  (No proxy nodes found)")
        return
    for name, proxy_type, delay in items:
        delay_str = f" ({delay}ms)" if delay is not None else ""
        print(f"- [{proxy_type}] {name}{delay_str}")


def cmd_switch(args: argparse.Namespace) -> None:
    group, node = resolve_switch_target(
        args.group_or_node, args.node, settings.default_group
    )
    with MihomoClient() as client:
        client.switch(group, node)
    print(f'Switched proxy group "{group}" to "{node}"')


def cmd_unpin(args: argparse.Namespace) -> None:
    with MihomoClient() as client:
        group = client.get_group(args.group)
        if not group.fixed:
            print(f'Proxy group "{group.name}" is not pinned')
            return
        client.unpin(group.name)
    print(f'Unpinned proxy group "{group.name}"')


def cmd_tui(_args: argparse.Namespace) -> None:
    try:
        from mihomo_ctrl.tui import run_tui
    except ImportError as exc:
        raise MihomoError(
            "TUI 需要 textual。请按 README 安装（含 TUI）；"
            "开发环境执行 uv sync --extra tui"
        ) from exc
    run_tui()


def cmd_reset(args: argparse.Namespace) -> None:
    path = Path(args.path).expanduser() if args.path else detect_cache_path()
    target = path.resolve()
    if reset_cache(target):
        print(f"[SUCCESS] Removed cache file: {target}")
        print("Tip: Restart Mihomo to restore default configuration states.")
    else:
        print(f"[INFO] Cache file not found: {target} (already clean)")


class VersionAction(argparse.Action):
    def __init__(self, option_strings: list[str], dest: str, **_kwargs: object) -> None:
        super().__init__(
            option_strings,
            dest=argparse.SUPPRESS,
            default=argparse.SUPPRESS,
            nargs=0,
            help="显示版本号并退出",
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        _namespace: argparse.Namespace,
        _values: object,
        _option_string: str | None = None,
    ) -> None:
        from importlib.metadata import PackageNotFoundError, version

        try:
            pkg_version = version("mihomo-ctrl")
        except PackageNotFoundError:
            pkg_version = "unknown"
        print(f"{parser.prog} {pkg_version}")
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mihomo CLI 控制工具。用 --help 即可当作 SKILL。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""建议操作流程（观察 → 调整 → 重试 → 复原）:
  1. 观察   mihomo-ctrl lsg
            记下入口组（常见是「默认」）现在的指向。
  2. 调整   代理结构存在分层（如「默认」→「自动选择」→ 香港节点，
            「默认」→「美国」→ 具体美国节点），禁止跨层级直接指定叶子节点。
            若目标地区组内选项不健康，先切地区组：
              mihomo-ctrl switch 美国 '<节点名>'
            再将默认组切到该地区：
              mihomo-ctrl switch 默认 美国
  3. 重试   切完后重跑刚才失败的网络请求。
  4. 复原   任务完成后必须将代理恢复原状，例如：
              mihomo-ctrl switch 默认 自动选择
            对 URLTest / Fallback 组执行过 switch 会钉死该组，
            用 unpin 取消钉死、恢复自动选择。
            不要执行 reset（会删 cache.db，只留给人）。
            不要执行 tui（给人用的界面）。

示例:
  mihomo-ctrl lsg
  mihomo-ctrl lsg 默认
  mihomo-ctrl ls
  mihomo-ctrl switch 默认 美国
  mihomo-ctrl switch 美国 '<节点名>'
  mihomo-ctrl unpin 自动选择
""",
    )
    parser.add_argument("-V", "--version", action=VersionAction)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_groups = subparsers.add_parser(
        "list-proxy-groups",
        aliases=["lsg"],
        help="列出代理组及各组的选中选项；带组名则按延迟列出该组选项",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="列出代理组，或按延迟列出指定组内的选项。",
    )
    p_groups.add_argument("group", nargs="?", help="代理组名（省略则列出所有代理组）")
    p_groups.set_defaults(func=cmd_list_proxy_groups)

    p_proxies = subparsers.add_parser(
        "list-proxies",
        aliases=["ls"],
        help="按延迟排序列出所有节点",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="按延迟排序列出节点（独立代理，不含代理组）。",
    )
    p_proxies.set_defaults(func=cmd_list_proxies)

    p_switch = subparsers.add_parser(
        "switch",
        help="切换指定代理组的选中选项",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="切换指定代理组的选中选项（第二个参数可以是节点或另一代理组）。",
    )
    p_switch.add_argument(
        "group_or_node",
        help="代理组名（只传一个参数时视为默认组下的选项）",
    )
    p_switch.add_argument("node", nargs="?", help="要选中的选项（节点或代理组）")
    p_switch.set_defaults(func=cmd_switch)

    p_unpin = subparsers.add_parser(
        "unpin",
        help="取消 URLTest/Fallback 组的钉死，恢复自动选择",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="取消指定代理组的钉死。未钉死则什么也不做。",
    )
    p_unpin.add_argument("group", help="代理组名")
    p_unpin.set_defaults(func=cmd_unpin)

    p_reset = subparsers.add_parser(
        "reset",
        aliases=["clear-cache"],
        help="删除 cache.db（只留给人，Agent 不要用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="定位并删除 cache.db。只留给人在配置搞乱时使用。",
    )
    p_reset.add_argument("path", nargs="?", help="cache.db 路径（省略则自动查找）")
    p_reset.set_defaults(func=cmd_reset)

    p_tui = subparsers.add_parser(
        "tui",
        help="给人用的界面（不要告诉 Agent）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="给人用的终端界面。Agent 请用 lsg / ls / switch / unpin。",
    )
    p_tui.set_defaults(func=cmd_tui)
    return parser


def _print_groups(groups: list[ProxyGroup]) -> None:
    print("=== Mihomo Proxy Groups ===")
    if not groups:
        print("  (No Proxy Groups found)")
        return
    for group in groups:
        mark = " *" if group.fixed else ""
        print(f"- [{group.proxy_type}] {group.name} -> {group.now}{mark}")


def main() -> None:
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    try:
        args.func(args)
    except MihomoAPIError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    except MihomoError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
