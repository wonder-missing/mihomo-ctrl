#!/usr/bin/env bash
# 安装 mihomo-ctrl（含给人用的 TUI）。
# 没有 uv 时会先安装 uv，并在继续前询问确认。
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/wonder-missing/mihomo-ctrl/main/install.sh | bash
set -euo pipefail

REPO="${MIHOMO_CTRL_REPO:-wonder-missing/mihomo-ctrl}"
UV_URL="https://astral.sh/uv/install.sh"

say() {
    printf '%s\n' "$*"
}

die() {
    printf 'install.sh: %s\n' "$*" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "需要 $1"
}

confirm_install_uv() {
    say ""
    say "未找到 uv。继续将安装 uv 到 ~/.local/bin。"
    say "uv 是独立的 Python 包管理器，不会改动系统自带的 Python。"
    say "随后会用 uv 安装 mihomo-ctrl（优先使用你已有的 Python 3.9+）。"
    say ""
    if [ "${CONFIRM_INSTALL_UV:-}" = "1" ]; then
        return 0
    fi
    if [ ! -r /dev/tty ]; then
        die "非交互环境且未安装 uv。请先自行安装 uv，或设置 CONFIRM_INSTALL_UV=1 后重试。"
    fi
    printf '是否继续安装 uv？[y/N] ' >/dev/tty
    read -r ans </dev/tty
    case "${ans}" in
        y|Y|yes|YES) ;;
        *) die "已取消。也可先安装 uv，再执行：uv tool install \"mihomo-ctrl[tui] @ git+https://github.com/${REPO}\"" ;;
    esac
}

need_cmd curl
need_cmd sh

export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
    confirm_install_uv
    say "正在安装 uv…"
    curl -LsSf "${UV_URL}" | sh
    export PATH="${HOME}/.local/bin:${PATH}"
    command -v uv >/dev/null 2>&1 || die "uv 安装后仍不在 PATH，请新开一个终端再执行本脚本"
fi

say "正在安装 mihomo-ctrl[tui]（git+https://github.com/${REPO}）…"
uv tool install --force "mihomo-ctrl[tui] @ git+https://github.com/${REPO}"

BIN="$(command -v mihomo-ctrl || true)"
if [ -z "${BIN}" ]; then
    die "安装完成但找不到 mihomo-ctrl。请把 ${HOME}/.local/bin 加进 PATH 后重试。"
fi

say ""
say "Installed: ${BIN}"
say "For Agent: mihomo-ctrl --help"
say "For Human: mihomo-ctrl tui"
say ""
say "Check whether ~/.local/bin is in your PATH."
