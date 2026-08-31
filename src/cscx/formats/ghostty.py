"""ghostty config — `key = value`, with an indexed `palette = N=#hex` form."""

from __future__ import annotations

import re

from ..color import ColorParseError, parse_color
from ..palette import Palette
from ._util import config_lines, decode, split_kv

NAME = "ghostty"
ALIASES = ()
EXTENSIONS = (".conf", "")
BINARY = False

_SCALARS = {
    "background": "background",
    "foreground": "foreground",
    "cursor-color": "cursor",
    "cursor-text": "cursor_text",
    "selection-background": "selection_background",
    "selection-foreground": "selection_foreground",
}

_RE_PALETTE_ENTRY = re.compile(r"^\s*(\d{1,3})\s*=\s*(.+?)\s*$")


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    if filename and filename.lower() in {"config", "ghostty.conf"}:
        base = 0.6
    else:
        base = 0.0

    # ghostty's config is flat; a section header means some INI format instead
    # (foot in particular shares ghostty's kebab-case selection-* keys).
    if re.search(r"(?m)^\s*\[[\w.\- ]+\]\s*$", text):
        return 0.0

    entries = len(re.findall(r"(?m)^\s*palette\s*=\s*\d{1,3}\s*=", text))
    if entries:
        return min(0.6 + entries * 0.025, 0.95)

    # No palette lines: fall back to ghostty's distinctive kebab-case keys.
    kebab = re.findall(
        r"(?m)^\s*(cursor-color|selection-background|selection-foreground|"
        r"background-opacity|window-decoration|font-family)\s*=",
        text,
    )
    if kebab:
        return min(base + 0.4 + len(kebab) * 0.05, 0.9)
    return base


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    palette = Palette(name=name, source_format=NAME)

    for _lineno, line in config_lines(text):
        pair = split_kv(line, separators="=")
        if pair is None:
            continue
        key, value = pair
        key = key.lower()

        if key == "palette":
            if m := _RE_PALETTE_ENTRY.match(value):
                index = int(m.group(1))
                if index <= 255:
                    palette.set_indexed(index, _safe_color(m.group(2)))
            continue

        if key in _SCALARS:
            setattr(palette, _SCALARS[key], _safe_color(value))
            continue

        if key == "background-opacity":
            try:
                palette.extras.setdefault("ghostty", {})["background-opacity"] = float(value)
            except ValueError:
                pass
        elif key == "theme":
            # Records that the real colors live in a named theme file we were
            # not given, so a caller can tell "no colors" from "colors elsewhere".
            palette.extras.setdefault("ghostty", {})["theme"] = value

    return palette


def _safe_color(value: str):
    try:
        return parse_color(value)
    except ColorParseError:
        return None
