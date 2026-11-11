"""Mihomo CLI 入口。--help 输出应能充当一份 SKILL。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mihomo_ctrl.cache import detect_cache_path, reset_cache
from mihomo_ctrl.client import (
    LOG_READ_TIMEOUT,
    MihomoClient,
    ProxyGroup,
    cross_level_switch_target,
    nodes_for_group,
    uses_member_order,
)
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

        proxies = client.proxies()
        group = client.get_group(args.group, proxies)
        delays = client.delay_map()
        group_names = {
            name
            for name, info in proxies.items()
            if isinstance(info, dict) and "all" in info
        }
        print(f"=== Proxy Group: {group.name} ===")
        print(f"Type: {group.proxy_type}")
        print(f"Current: {group.now}")
        if group.fixed:
            print(f"Pinned: {group.fixed}")
        order = (
            "member"
            if uses_member_order(group.proxy_type, group.nodes, group_names)
            else "delay"
        )
        print(f"Order: {order}")
        print("Options:")
        for node in nodes_for_group(
            group.proxy_type, group.nodes, delays, group_names
        ):
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
        index = client.proxy_index()
        current = client.get_group(group, index)
        if not args.force and cross_level_switch_target(current, node, index):
            raise MihomoError(
                f'Refusing cross-level switch: "{group}" 是聚合组，'
                f'直接切到叶子 "{node}" 会跳过地区层（还会被 store-selected 记住）。'
                f"先切地区组、再把 {group} 切到该地区；确实要这样切用 --force。"
            )
        client.switch(group, node)
        landed = client.get_group(group).now
    if landed != node:
        raise MihomoError(
            f'Switch did not stick: "{group}" 现在指向 "{landed}"（不是 "{node}"）。'
            "多半是目标不健康，Mihomo 当场丢弃了这次指定。"
        )
    print(f'Switched proxy group "{group}" to "{node}"')


def cmd_unpin(args: argparse.Namespace) -> None:
    with MihomoClient() as client:
        group = client.get_group(args.group)
        if not group.fixed:
            print(f'Proxy group "{group.name}" is not pinned')
            return
        client.unpin(group.name)
        still = client.get_group(group.name).fixed
    if still:
        raise MihomoError(f'Unpin did not stick: "{group.name}" 仍钉在 "{still}"。')
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


def cmd_logs(args: argparse.Namespace) -> None:
    # -f 持续跟随。接口没有历史，-n 无法先回放再跟，所以跟随时不截断。
    limit = None if args.follow else args.lines
    try:
        with MihomoClient() as client:
            for line in client.read_logs(level=args.level, limit=limit):
                print(line, flush=True)
    except BrokenPipeError:
        return
    except KeyboardInterrupt:
        return


def cmd_reload(args: argparse.Namespace) -> None:
    raw = args.path or ""
    path = str(Path(raw).expanduser()) if raw else ""
    if path and not Path(path).is_absolute():
        raise MihomoError(f"配置路径必须是绝对路径: {path}")
    with MihomoClient() as client:
        client.reload(path)
    if path:
        print(f"Reloaded config: {path}")
    else:
        print("Reloaded startup config")


def cmd_reset(args: argparse.Namespace) -> None:
    path = Path(args.path).expanduser() if args.path else detect_cache_path()
    target = path.resolve()
    if reset_cache(target):
        print(f"[SUCCESS] Removed cache file: {target}")
        print("Tip: store-selected 的全部指向（含手选、钉死）随之丢失；")
        print("     重启 Mihomo 后各回默认状态。")
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
            「默认」→「美国」→ 具体美国节点），禁止跨层级直接指定叶子节点
            （工具会拒绝这类切换；确实要切加 --force）。
            若目标地区组内选项不健康，先切地区组：
              mihomo-ctrl switch 美国 '<节点名>'
            再将默认组切到该地区：
              mihomo-ctrl switch 默认 美国
  3. 重试   切完后重跑刚才失败的网络请求。
            switch / unpin 会复核结果：没生效会报 "did not stick" 并以非零退出，
            就当没切成（通常是目标不健康，Mihomo 当场丢弃了这次指定）。
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
  mihomo-ctrl logs -n 20
  mihomo-ctrl logs -f
  mihomo-ctrl reload
  mihomo-ctrl reload /absolute/path/config.yaml

环境变量（装好的 CLI 只读 shell 环境；仓库里 uv run 会额外加载 .env）:
  MIHOMO_API_URL        External Controller 地址（默认 http://127.0.0.1:9090）
  MIHOMO_SECRET         Controller 的 secret（默认空）
  MIHOMO_DEFAULT_GROUP  单参 switch 的默认组（默认 PROXY，按自己的入口组名设置）
""",
    )
    parser.add_argument("-V", "--version", action=VersionAction)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_groups = subparsers.add_parser(
        "list-proxy-groups",
        aliases=["lsg"],
        help="列出代理组及各组的选中选项；带组名则按该组策略列出选项",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "列出代理组。指定组名时，Fallback 和含组的 Selector 按成员顺序；"
            "URLTest 和纯叶子 Selector 按延迟。延迟仍附在名字后面。"
        ),
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
    p_switch.add_argument(
        "--force",
        action="store_true",
        help="允许聚合组直切叶子节点（默认拒绝跨层级；只给清楚后果的人用）",
    )
    p_switch.set_defaults(func=cmd_switch)

    p_unpin = subparsers.add_parser(
        "unpin",
        help="取消 URLTest/Fallback 组的钉死，恢复自动选择",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="取消指定代理组的钉死。未钉死则什么也不做。",
    )
    p_unpin.add_argument("group", help="代理组名")
    p_unpin.set_defaults(func=cmd_unpin)

    idle = f"{LOG_READ_TIMEOUT:g}"
    p_logs = subparsers.add_parser(
        "logs",
        help="打印实时日志；-n 收满退出，-f 持续跟随",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "打印实时日志（GET /logs）。接口只推送连上之后的新日志，没有历史。\n"
            f"不带 -f 时最多打印 N 行（默认 10）；安静超过 {idle} 秒没新日志也会停。\n"
            "带 -f 时持续跟随，直到中断；此时 -n 不截断。"
        ),
    )
    p_logs.add_argument(
        "-n",
        "--lines",
        type=_positive_int,
        default=10,
        metavar="N",
        help="最多打印的行数（默认 10）。只在不带 -f 时生效",
    )
    p_logs.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="持续跟随，直到中断",
    )
    p_logs.add_argument(
        "--level",
        choices=("debug", "info", "warning", "error"),
        help="最低级别（省略则由内核默认，通常是 info）",
    )
    p_logs.set_defaults(func=cmd_logs)

    p_reload = subparsers.add_parser(
        "reload",
        help="重载配置（PUT /configs?force=true）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "重载配置：PUT /configs?force=true，正文 {\"path\", \"payload\"}。\n"
            "省略路径时 path 为空，内核重载自己启动时的那份配置"
            "（-d 目录下的 config.yaml）。\n"
            "传入的路径必须是绝对路径，且在内核的安全路径内。"
        ),
    )
    p_reload.add_argument(
        "path",
        nargs="?",
        help="配置文件绝对路径（省略则重载启动时的那份）",
    )
    p_reload.set_defaults(func=cmd_reload)

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


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("行数必须是正整数") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("行数必须是正整数")
    return number


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
