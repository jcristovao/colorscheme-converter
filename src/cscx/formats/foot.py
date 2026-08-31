"""foot.ini — a `[colors]` section of bare `rrggbb` values."""

from __future__ import annotations

import configparser
import re

from ..color import ColorParseError, parse_color
from ..palette import Palette
from ._util import decode

NAME = "foot"
ALIASES = ("foot.ini",)
EXTENSIONS = (".ini",)
BINARY = False

# foot allows bare keys before the first section, which configparser rejects.
_TOP_SECTION = "__toplevel__"

_RE_SLOT = re.compile(r"^(regular|bright|dim)([0-7])$")

_SCALARS = {
    "background": "background",
    "foreground": "foreground",
    "selection-foreground": "selection_foreground",
    "selection-background": "selection_background",
}


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    if filename and filename.lower() == "foot.ini":
        return 0.95
    if not re.search(r"(?m)^\s*\[colors\]", text):
        return 0.0
    slots = len(re.findall(r"(?m)^\s*(regular|bright)[0-7]\s*=", text))
    return min(0.6 + slots * 0.02, 0.93) if slots else 0.45


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(f"[{_TOP_SECTION}]\n{text}")

    palette = Palette(name=name, source_format=NAME)
    if not parser.has_section("colors"):
        return palette

    for key, value in parser.items("colors"):
        key = key.strip().lower()

        if m := _RE_SLOT.match(key):
            group, slot = m.group(1), int(m.group(2))
            color = _safe_color(value)
            if group == "dim":
                palette.dim[slot] = color
            else:
                palette.set_ansi(slot + (8 if group == "bright" else 0), color)
            continue

        if key.isdigit():
            # foot spells the extended palette as bare `16 = rrggbb` keys.
            index = int(key)
            if index <= 255:
                palette.set_indexed(index, _safe_color(value))
            continue

        if key in _SCALARS:
            setattr(palette, _SCALARS[key], _safe_color(value))
        elif key == "alpha":
            try:
                palette.extras.setdefault("foot", {})["alpha"] = float(value)
            except ValueError:
                pass
        elif (color := _safe_color(value)) is not None:
            palette.extras.setdefault("foot", {})[key] = color.hex

    # foot writes the cursor as `color=<text> <cursor>`, in that order.
    for section in ("cursor", "colors"):
        if parser.has_section(section) and parser.has_option(section, "color"):
            parts = parser.get(section, "color").split()
            if len(parts) == 2:
                palette.cursor_text = _safe_color(parts[0])
                palette.cursor = _safe_color(parts[1])
            break

    return palette


def _safe_color(value: str):
    try:
        return parse_color(value)
    except ColorParseError:
        return None
