#!/usr/bin/env bash
# 生成 README / 社交分享用的 CLI 演示 GIF（合成画面，不连接真实 Mihomo）。
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p docs
uv run --with pillow python "$ROOT/scripts/record-demo.py" --title mihomo-ctrl --out "${1:-"$ROOT/docs/demo.gif"}"
