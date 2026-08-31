"""X resources — `*color0: #hex` lines, as used by xterm, urxvt and xrdb."""

from __future__ import annotations

import re

from ..color import ColorParseError, parse_color
from ..palette import Palette
from ._util import decode

NAME = "xresources"
ALIASES = ("xdefaults", "xrdb")
EXTENSIONS = (".xresources", ".xdefaults", ".Xresources")
BINARY = False

_RE_RESOURCE = re.compile(r"^\s*([\w*.\-]+)\s*:\s*(.+?)\s*$")
_RE_COLOR_N = re.compile(r"^color(\d{1,3})$")

_SCALARS = {
    "foreground": "foreground",
    "background": "background",
    "cursorcolor": "cursor",
    "cursorcolour": "cursor",
    "pointercolor": "cursor",
    "highlightcolor": "selection_background",
    "highlighttextcolor": "selection_foreground",
}


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    if filename and filename.lower().lstrip(".") in {"xresources", "xdefaults"}:
        return 0.9
    hits = len(re.findall(r"(?m)^\s*[\w*.\-]*[*.]color\d{1,3}\s*:", text))
    if hits:
        return min(0.6 + hits * 0.02, 0.92)
    if re.search(r"(?m)^\s*[\w*.\-]*[*.](foreground|background)\s*:\s*#[0-9a-fA-F]{3,6}", text):
        return 0.5
    return 0.0


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    palette = Palette(name=name, source_format=NAME)

    for raw in text.splitlines():
        line = raw.strip()
        # `!` is the X resource comment; `#` starts a cpp directive here, not
        # a color, because every value in this format sits after a colon.
        if not line or line[0] in "!#":
            continue
        m = _RE_RESOURCE.match(line)
        if not m:
            continue

        resource, value = m.groups()
        # Keep only the final component: `URxvt*color1` and `*.color1` agree.
        key = re.split(r"[*.]", resource)[-1].strip().lower()
        if not key:
            continue

        if n := _RE_COLOR_N.match(key):
            index = int(n.group(1))
            if index <= 255:
                palette.set_indexed(index, _safe_color(value))
        elif key in _SCALARS:
            setattr(palette, _SCALARS[key], _safe_color(value))
        elif key in {"colorbd", "colorul", "colorit", "fadecolor", "bordercolor"}:
            if (color := _safe_color(value)) is not None:
                palette.extras.setdefault("xresources", {})[key] = color.hex

    return palette


def _safe_color(value: str):
    try:
        return parse_color(value)
    except ColorParseError:
        return None
