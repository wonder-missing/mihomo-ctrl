#!/usr/bin/env python3
"""Overlay a window-bar title on a VHS GIF without a Pillow GIF re-encode.

VHS writes a small, delta-compressed GIF. Rewriting frames with Pillow
inflates it several times. Title text is a PNG; ffmpeg overlays it and
rebuilds the palette.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TITLE = "mihomo-ctrl"
BAR_H = 40
DIM = (108, 112, 134)
FONT_PATH = "/System/Library/Fonts/Menlo.ttc"
TITLE_SIZE = 16


def _title_png(path: Path, width: int, title: str, bar_h: int) -> None:
    overlay = Image.new("RGBA", (width, bar_h), (0, 0, 0, 0))
    font = ImageFont.truetype(FONT_PATH, size=TITLE_SIZE, index=0)
    draw = ImageDraw.Draw(overlay)
    left, top, right, bottom = font.getbbox(title)
    text_w = right - left
    text_h = bottom - top
    x = (width - text_w) / 2 - left
    y = (bar_h - text_h) / 2 - top
    draw.text((x, y), title, font=font, fill=(*DIM, 255))
    overlay.save(path)


def stamp(path: Path, title: str = TITLE, bar_h: int = BAR_H) -> None:
    gif = Image.open(path)
    width, _height = gif.size
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp) / "title.png"
        stamped = Path(tmp) / "stamped.gif"
        _title_png(overlay, width, title, bar_h)
        vf = (
            "[0][1]overlay=0:0,split[s0][s1];"
            "[s0]palettegen=max_colors=256:stats_mode=full[p];"
            "[s1][p]paletteuse=dither=none"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-i",
                str(overlay),
                "-filter_complex",
                vf,
                "-loop",
                "0",
                str(stamped),
            ],
            check=True,
        )
        path.write_bytes(stamped.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gif", type=Path)
    parser.add_argument("--title", default=TITLE)
    args = parser.parse_args()
    if not args.gif.is_file():
        print(f"missing gif: {args.gif}", file=sys.stderr)
        sys.exit(1)
    stamp(args.gif, title=args.title)


if __name__ == "__main__":
    main()
