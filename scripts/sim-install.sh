#!/usr/bin/env bash
# 临时变成一个干净用户，彩排 install.sh。
#
# 本机已有 Homebrew uv 和真 ~/.local。直接跑 install.sh 会走错路、写错地方：
# 已经有 uv 就测不到「先装 uv」；不换 HOME 会往真家里写。
# 做法：假 HOME + 瘦 PATH，把本机 uv 藏起来。系统 python3 仍可用。
#
# 两场：
#   默认    假用户跑仓库里的 install.sh（从 GitHub 拉已发布的包）
#   --local 第一场之后卸掉，改用当前工作区，并钉死 Python 3.9
#
# 用法（仓库根目录）：
#   ./scripts/sim-install.sh
#   ./scripts/sim-install.sh --local
#
# 回滚：rm -rf /tmp/mihomo-ctrl-install-sim
set -euo pipefail

# CDPATH 若有值，cd 可能跑偏或往 stdout 打路径。
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
SIM="${SIM_DIR:-/tmp/mihomo-ctrl-install-sim}"
HOME_DIR="$SIM/home"
LOCAL=0

for arg in "$@"; do
    case "$arg" in
        --local) LOCAL=1 ;;
        -h|--help)
            # 文件头注释就是 --help（到 set -euo 为止，避免写死行号）。
            sed -n '2,/^set -euo pipefail$/p' "$0" | sed '$d'
            exit 0
            ;;
        *)
            printf '未知参数: %s\n' "$arg" >&2
            exit 1
            ;;
    esac
done

# 假家。后面 uv / XDG 都写这里，不是真 ~。
rm -rf "$HOME_DIR"
mkdir -p "$HOME_DIR"
export HOME="$HOME_DIR"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_CONFIG_HOME="$HOME/.config"

# 官方 uv 安装器若看到 UV_INSTALL_DIR，会把二进制直接扔进该目录
#（不是该目录/bin），而 install.sh 只把 ~/.local/bin 加进 PATH。
unset UV_INSTALL_DIR

# 瘦 PATH：只留系统目录 + 假 ~/.local/bin，本机 Homebrew uv 就看不见了。
export PATH="/usr/bin:/bin:$HOME/.local/bin"
# bash 缓存了命令路径；PATH 改了不清缓存，command -v uv 仍可能命中旧位置。
hash -r

{
    echo "==== 模拟环境 ===="
    echo "HOME=$HOME"
    echo "PATH=$PATH"
    echo -n "python3: "
    command -v python3
    python3 -V
    echo -n "uv before: "
    command -v uv || echo "(none)"
} | tee "$SIM/before.txt"

if command -v uv >/dev/null 2>&1; then
    echo "PATH 上仍能看到 uv，模拟失败。" >&2
    exit 1
fi

echo ""
echo "==== 第一场：执行 $ROOT/install.sh ===="
# install.sh 没找到 uv 会问要不要装；非交互下用这个自动同意。
export CONFIRM_INSTALL_UV=1
"$ROOT/install.sh" 2>&1 | tee "$SIM/install.log"
echo "INSTALL_EXIT:$?" | tee -a "$SIM/install.log"

if [ "$LOCAL" -eq 1 ]; then
    echo ""
    echo "==== 第二场：卸掉 GitHub 版，改用当前仓库 + Python 3.9 ===="
    uv tool uninstall mihomo-ctrl
    uv tool install --force --python 3.9 \
        "mihomo-ctrl[tui] @ ${ROOT}" 2>&1 | tee "$SIM/install-local-39.log"
fi

{
    echo "==== 结果 ===="
    command -v uv
    uv --version
    command -v mihomo-ctrl
    uv tool list
    echo "---- shebang ----"
    head -1 "$(command -v mihomo-ctrl)"
    echo "---- --help ----"
    mihomo-ctrl --help | head -8
} | tee "$SIM/after.txt"

echo ""
echo "回滚：rm -rf $SIM"
echo "本机 uv 应仍在原处（常见：/opt/homebrew/bin/uv）。"
