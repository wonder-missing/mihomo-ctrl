#!/usr/bin/env bash
# Pillow 合成版演示 GIF：逐字符绘帧，不连 Mihomo，也不需要 vhs。
# 相同像素做成透明差分（无损）；若有 gifsicle 再跑一遍 -O3。
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p docs
uv run --with pillow python "$ROOT/scripts/demo-pillow.py" --title mihomo-ctrl --out "${1:-"$ROOT/docs/demo.gif"}"
