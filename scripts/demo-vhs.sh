#!/usr/bin/env bash
# VHS 实录版演示 GIF：假 Mihomo API + 真实 CLI/TUI PTY。
# 故事与 scripts/demo-pillow.py 相同。
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${DEMO_FIXTURE_PORT:-18765}"
BIN="$ROOT/.demo-bin"
TAPE="$ROOT/scripts/demo-vhs.tape"
OUT="${1:-"$ROOT/docs/demo.gif"}"
mkdir -p "$BIN" docs

if [ ! -x "$ROOT/.venv/bin/mihomo-ctrl" ]; then
    uv sync --extra tui
fi

cat > "$BIN/mihomo-ctrl" <<EOF
#!/usr/bin/env bash
export MIHOMO_API_URL="http://127.0.0.1:${PORT}"
unset NO_COLOR CLICOLOR CLICOLOR_FORCE FORCE_COLOR
export COLORTERM=truecolor
export TERM=xterm-256color
exec "$ROOT/.venv/bin/mihomo-ctrl" "\$@"
EOF
chmod +x "$BIN/mihomo-ctrl"

cat > "$ROOT/.demo-env" <<EOF
export PATH="${BIN}:\$PATH"
export MIHOMO_API_URL="http://127.0.0.1:${PORT}"
export PS1='\[\e[38;2;137;220;235m\]\$ \[\e[0m\]'
export TERM=xterm-256color
export COLORTERM=truecolor
unset NO_COLOR CLICOLOR CLICOLOR_FORCE FORCE_COLOR
EOF

uv run python "$ROOT/scripts/demo-vhs-fixture.py" --port "$PORT" &
FIXTURE_PID=$!
cleanup() {
    kill "$FIXTURE_PID" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for _ in $(seq 1 25); do
    if curl -sf "http://127.0.0.1:${PORT}/proxies" >/dev/null; then
        ready=1
        break
    fi
    sleep 0.15
done
if [ "$ready" -ne 1 ]; then
    echo "fixture did not start on port ${PORT}" >&2
    exit 1
fi

export PATH="$BIN:$PATH"
export MIHOMO_API_URL="http://127.0.0.1:${PORT}"
# Agent / CI shells export NO_COLOR; Textual then paints the TUI monochrome.
unset NO_COLOR CLICOLOR CLICOLOR_FORCE
export COLORTERM=truecolor
export TERM=xterm-256color
vhs validate "$TAPE"
vhs -o "$OUT" "$TAPE"

# VHS 窗口栏没有标题接口；合成后写上项目名。
uv run --with pillow python "$ROOT/scripts/demo-vhs-stamp.py" "$OUT"
