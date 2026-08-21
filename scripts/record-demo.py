"""Synthesize a looping terminal CLI demo GIF. Does not capture a live session."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 4:3，接近日常终端；CLI 字号沿用已定稿的 1.2 倍，TUI 定妆单独缩小。
WIDTH, HEIGHT = 960, 720


def _s(n: int) -> int:
    return round(n * 1280 / 960)


PAD_X, CHROME_H, PAD_TOP = _s(28), _s(40), _s(16)
FONT_SIZE = round(_s(17) * 1.2)
TITLE_SIZE = round(_s(13) * 1.2)
LINE_H = round(_s(26) * 1.2)
DOT_R = _s(6)
PROMPT = "$ "

BG = (24, 24, 37)
CHROME = (17, 17, 27)
TEXT = (205, 214, 244)
DIM = (108, 112, 134)
CYAN = (137, 220, 235)
GREEN = (166, 227, 161)
YELLOW = (249, 226, 175)
BLUE = (137, 180, 250)
MAUVE = (203, 166, 247)
SURFACE = (49, 50, 68)
RED_DOT = (243, 139, 168)
YELLOW_DOT = (249, 226, 175)
GREEN_DOT = (166, 227, 161)

LATIN_FONTS = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Courier.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)
CJK_FONTS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


@dataclass
class TypeCmd:
    text: str


@dataclass
class Output:
    text: str


@dataclass
class Wait:
    ms: int


@dataclass
class Clear:
    pass


@dataclass
class Screen:
    """Replace the buffer with these lines and hold. Use for a TUI still."""

    text: str
    ms: int = 3000


@dataclass
class TuiStill:
    ms: int = 3000


Step = TypeCmd | Output | Wait | Clear | Screen | TuiStill

SCENE: list[Step] = [
    TypeCmd("mihomo-ctrl lsg"),
    Output(
        "=== Mihomo Proxy Groups ===\n"
        "- [Selector] 默认 -> 自动选择\n"
        "- [URLTest] 自动选择 -> HK-02 *\n"
        "- [Selector] 香港 -> HK-02\n"
        "- [Selector] 美国 -> US-01"
    ),
    Wait(2800),
    Clear(),
    TypeCmd("mihomo-ctrl lsg 美国"),
    Output(
        "=== Proxy Group: 美国 ===\n"
        "Type: Selector\n"
        "Current: US-01\n"
        "Options:\n"
        "  [ ] US-02 (28ms)\n"
        "  [*] US-01 (67ms)\n"
        "  [ ] US-03 (142ms)"
    ),
    Wait(3200),
    Clear(),
    TypeCmd("mihomo-ctrl switch 默认 美国"),
    Output('Switched proxy group "默认" to "美国"'),
    Wait(2000),
    TypeCmd("mihomo-ctrl lsg"),
    Output(
        "=== Mihomo Proxy Groups ===\n"
        "- [Selector] 默认 -> 美国\n"
        "- [URLTest] 自动选择 -> HK-02 *\n"
        "- [Selector] 香港 -> HK-02\n"
        "- [Selector] 美国 -> US-01"
    ),
    Wait(2800),
    Clear(),
    TypeCmd("mihomo-ctrl tui"),
    Wait(400),
    TuiStill(3000),
]


def _load_font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    last_error: Exception | None = None
    for path in candidates:
        if not Path(path).exists():
            continue
        try:
            return ImageFont.truetype(path, size=size, index=0)
        except OSError as exc:
            last_error = exc
    raise FileNotFoundError(
        f"no usable font in {candidates}"
        + (f" ({last_error})" if last_error else "")
    )


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2CEAF
    )


class TerminalView:
    def __init__(
        self,
        title: str,
        font_size: int = FONT_SIZE,
        line_h: int = LINE_H,
    ) -> None:
        self.title_text = title
        self.line_h = line_h
        self.latin = _load_font(LATIN_FONTS, font_size)
        self.cjk = _load_font(CJK_FONTS, font_size)
        self.title = _load_font(LATIN_FONTS, TITLE_SIZE)
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        self.cell_w = float(probe.textlength("M", font=self.latin))
        ink_bottom = 0
        for char in "Mg$國":
            _left, _top, _right, bottom = self.font_for(char).getbbox(char)
            ink_bottom = max(ink_bottom, bottom)
        self.cursor_h = max(ink_bottom, 1)
        self.lines: list[str] = []
        self.prompt_cmd: str | None = None
        self.cursor_on = True

    def font_for(self, char: str) -> ImageFont.FreeTypeFont:
        return self.cjk if _is_cjk(char) else self.latin

    def visible_rows(self) -> int:
        return max(1, (HEIGHT - CHROME_H - PAD_TOP - _s(18)) // self.line_h)

    def snapshot_lines(self) -> list[str]:
        extra = 1 if self.prompt_cmd is not None else 0
        body = self.lines
        overflow = len(body) + extra - self.visible_rows()
        if overflow > 0:
            body = body[overflow:]
        return body


_TOKEN_RE = re.compile(r"(\[[^\]]+\]|->|\(\d+ms\)|===+|\*)")


def _token_color(token: str) -> tuple[int, int, int]:
    if token.startswith("[*") and token.endswith("]"):
        return GREEN
    if token == "[ ]":
        return DIM
    if token == "[URLTest]":
        return MAUVE
    if token.startswith("[") and token.endswith("]"):
        return BLUE
    if token == "->":
        return DIM
    if token.startswith("(") and token.endswith("ms)"):
        return YELLOW
    if token == "*":
        return GREEN
    if set(token) <= {"="}:
        return DIM
    return TEXT


def _line_color(line: str) -> tuple[int, int, int]:
    stripped = line.strip()
    if stripped.startswith("Switched "):
        return GREEN
    if stripped.startswith("==="):
        return DIM
    if stripped in {"Options:"} or stripped.startswith("Type:"):
        return DIM
    return TEXT


def _draw_mixed(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    view: TerminalView,
    fill: tuple[int, int, int],
) -> float:
    x, y = xy
    for char in text:
        font = view.font_for(char)
        draw.text((x, y), char, font=font, fill=fill)
        x += float(draw.textlength(char, font=font))
    return x


def _draw_line(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    line: str,
    view: TerminalView,
) -> None:
    default = _line_color(line)
    cursor = 0
    for match in _TOKEN_RE.finditer(line):
        if match.start() > cursor:
            x = _draw_mixed(
                draw, (x, y), line[cursor : match.start()], view, default
            )
        token = match.group(0)
        x = _draw_mixed(draw, (x, y), token, view, _token_color(token))
        cursor = match.end()
    if cursor < len(line):
        _draw_mixed(draw, (x, y), line[cursor:], view, default)


def _draw_chrome(draw: ImageDraw.ImageDraw, view: TerminalView) -> None:
    draw.rectangle((0, 0, WIDTH, CHROME_H), fill=CHROME)
    for i, color in enumerate((RED_DOT, YELLOW_DOT, GREEN_DOT)):
        cx = PAD_X + DOT_R + i * _s(18)
        cy = CHROME_H // 2
        draw.ellipse((cx - DOT_R, cy - DOT_R, cx + DOT_R, cy + DOT_R), fill=color)
    title_w = draw.textlength(view.title_text, font=view.title)
    title_y = (CHROME_H - TITLE_SIZE) / 2
    draw.text(
        ((WIDTH - title_w) / 2, title_y),
        view.title_text,
        font=view.title,
        fill=DIM,
    )


def _mix(
    base: tuple[int, int, int], overlay: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    return tuple(
        int(base[i] * (1 - amount) + overlay[i] * amount) for i in range(3)
    )


def _text_width(text: str, view: TerminalView, draw: ImageDraw.ImageDraw) -> float:
    return sum(float(draw.textlength(c, font=view.font_for(c))) for c in text)


def _row_text_y(view: TerminalView, row_y: float) -> float:
    return row_y + max(0.0, (view.line_h - view.cursor_h) / 2)


def _tui_view(title: str) -> TerminalView:
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    inner = WIDTH - PAD_X * 2
    split = PAD_X + inner * 2 // 5
    left_w = split - PAD_X - _s(10)
    right_w = WIDTH - PAD_X - (split + _s(16))
    left_header = "mihomo-ctrl  4 个代理组"
    keys = "⏎ 选择  q 退出  r 刷新  u 消钉"
    group = "[URLTest] 自动选择  HK-02 *"
    node_title = "默认  ·  Selector  ·  当前 美国"
    for size in range(FONT_SIZE - 4, 12, -1):
        line_h = max(size + 8, round(LINE_H * size / FONT_SIZE))
        view = TerminalView(title, font_size=size, line_h=line_h)
        if _text_width(left_header, view, probe) + _text_width(keys, view, probe) + _s(
            24
        ) > inner:
            continue
        if _text_width(group, view, probe) > left_w:
            continue
        if _text_width(node_title, view, probe) > right_w:
            continue
        return view
    return TerminalView(title, font_size=13, line_h=20)


def render_tui_frame(chrome: TerminalView) -> Image.Image:
    view = _tui_view(chrome.title_text)
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    _draw_chrome(draw, chrome)
    y = CHROME_H + _s(8)
    header_ty = _row_text_y(view, y)
    x = _draw_mixed(draw, (PAD_X, header_ty), "mihomo-ctrl", view, TEXT)
    _draw_mixed(draw, (x, header_ty), "  4 个代理组", view, DIM)
    keys = "⏎ 选择  q 退出  r 刷新  u 消钉"
    keys_w = _text_width(keys, view, draw)
    _draw_mixed(draw, (WIDTH - PAD_X - keys_w, header_ty), keys, view, DIM)

    y += view.line_h + _s(6)
    inner_w = WIDTH - PAD_X * 2
    split = PAD_X + inner_w * 2 // 5
    divider = _mix(BG, BLUE, 0.28)
    draw.line((split, y, split, HEIGHT - _s(16)), fill=divider, width=_s(1))
    left_x = PAD_X
    right_x = split + _s(16)
    pane_ty = _row_text_y(view, y)
    _draw_mixed(draw, (left_x, pane_ty), "代理组  ↑↓", view, DIM)
    _draw_mixed(draw, (right_x, pane_ty), "默认  ·  Selector  ·  当前 美国", view, DIM)
    y += view.line_h

    groups = [
        ("[Selector]", "默认", "美国", True),
        ("[URLTest]", "自动选择", "HK-02 *", False),
        ("[Selector]", "香港", "HK-02", False),
        ("[Selector]", "美国", "US-01", False),
    ]
    nodes = [
        ("自动选择", False),
        ("香港", False),
        ("美国", True),
    ]
    row_y = y
    for type_tag, name, now, selected in groups:
        if selected:
            draw.rectangle(
                (
                    left_x - _s(6),
                    row_y,
                    split - _s(8),
                    row_y + view.line_h,
                ),
                fill=_mix(BG, BLUE, 0.32),
            )
        gx = left_x
        ty = _row_text_y(view, row_y)
        type_color = BLUE if selected else DIM
        gx = _draw_mixed(draw, (gx, ty), f"{type_tag} ", view, type_color)
        gx = _draw_mixed(draw, (gx, ty), f"{name}  ", view, TEXT)
        if now.endswith(" *"):
            gx = _draw_mixed(draw, (gx, ty), now[:-1], view, DIM)
            _draw_mixed(draw, (gx, ty), "*", view, GREEN)
        else:
            _draw_mixed(draw, (gx, ty), now, view, DIM)
        row_y += view.line_h

    row_y = y
    for name, current in nodes:
        if current:
            draw.rectangle(
                (
                    right_x - _s(6),
                    row_y,
                    WIDTH - PAD_X,
                    row_y + view.line_h,
                ),
                fill=_mix(BG, BLUE, 0.32),
            )
        nx = right_x
        ty = _row_text_y(view, row_y)
        mark = "● " if current else "  "
        nx = _draw_mixed(draw, (nx, ty), mark, view, GREEN if current else DIM)
        _draw_mixed(
            draw, (nx, ty), name, view, TEXT if current else DIM
        )
        row_y += view.line_h
    return img


def render_frame(view: TerminalView) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    _draw_chrome(draw, view)
    y = CHROME_H + PAD_TOP
    for line in view.snapshot_lines():
        _draw_line(draw, PAD_X, y, line, view)
        y += view.line_h
    if view.prompt_cmd is not None:
        x = _draw_mixed(draw, (PAD_X, y), PROMPT, view, CYAN)
        x = _draw_mixed(draw, (x, y), view.prompt_cmd, view, TEXT)
        if view.cursor_on:
            draw.rectangle(
                (x, y, x + view.cell_w, y + view.cursor_h),
                fill=SURFACE,
            )
    return img


def _extend(
    frames: list[Image.Image], durations: list[int], img: Image.Image, ms: int
) -> None:
    frames.append(img)
    durations.append(ms)


def build_frames(title: str, scene: list[Step]) -> tuple[list[Image.Image], list[int]]:
    view = TerminalView(title)
    frames: list[Image.Image] = []
    durations: list[int] = []
    view.prompt_cmd = ""
    _extend(frames, durations, render_frame(view), 400)

    for step in scene:
        if isinstance(step, Clear):
            view.lines = []
            view.prompt_cmd = ""
            _extend(frames, durations, render_frame(view), 240)
        elif isinstance(step, TypeCmd):
            view.prompt_cmd = ""
            view.cursor_on = True
            _extend(frames, durations, render_frame(view), 240)
            for index, char in enumerate(step.text):
                view.prompt_cmd += char
                pause = 70 if char == " " else 38
                if index == len(step.text) - 1:
                    pause = 220
                _extend(frames, durations, render_frame(view), pause)
            view.lines.append(f"{PROMPT}{step.text}")
            view.prompt_cmd = None
            _extend(frames, durations, render_frame(view), 140)
        elif isinstance(step, Output):
            for line in step.text.split("\n"):
                view.lines.append(line)
                _extend(frames, durations, render_frame(view), 70)
            view.lines.append("")
            _extend(frames, durations, render_frame(view), 200)
        elif isinstance(step, Screen):
            view.lines = list(step.text.split("\n"))
            view.prompt_cmd = None
            _extend(frames, durations, render_frame(view), step.ms)
        elif isinstance(step, TuiStill):
            _extend(frames, durations, render_tui_frame(view), step.ms)
        else:
            if view.prompt_cmd is None:
                view.prompt_cmd = ""
            view.cursor_on = True
            _extend(frames, durations, render_frame(view), step.ms)

    return frames, durations


def save_gif(frames: list[Image.Image], durations: list[int], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    palette = frames[-1].quantize(colors=48, method=Image.Quantize.MEDIANCUT)
    indexed = [
        frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames
    ]
    indexed[0].save(
        dest,
        save_all=True,
        append_images=indexed[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="mihomo-ctrl")
    parser.add_argument("--out", default="docs/demo.gif")
    args = parser.parse_args()
    dest = Path(args.out)
    frames, durations = build_frames(args.title, SCENE)
    save_gif(frames, durations, dest)
    size_kb = dest.stat().st_size / 1024
    print(f"wrote {dest} ({len(frames)} frames, {size_kb:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
