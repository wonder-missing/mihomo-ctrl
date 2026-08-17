#!/usr/bin/env bash
# 分别在 Python 3.9 和 3.14 上跑 pytest，不改开发目录里的 .venv。
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

failed=0
for py in 3.9 3.14; do
    echo "==== pytest (Python $py) ===="
    if ! uv run --python "$py" --isolated pytest "$@"; then
        failed=1
    fi
done
exit "$failed"
