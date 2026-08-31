"""iTerm2 .itermcolors — a plist of 0.0-1.0 float components."""

from __future__ import annotations

import plistlib
import re

from ..color import Color
from ..palette import Palette
from ._util import decode

NAME = "iterm2"
ALIASES = ("itermcolors", "iterm")
EXTENSIONS = (".itermcolors", ".plist")
BINARY = True

_RE_ANSI_KEY = re.compile(r"^Ansi (\d{1,3}) Color$")

_SCALARS = {
    "Background Color": "background",
    "Foreground Color": "foreground",
    "Cursor Color": "cursor",
    "Cursor Text Color": "cursor_text",
    "Selection Color": "selection_background",
    "Selected Text Color": "selection_foreground",
}

_EXTRA_KEYS = ("Bold Color", "Link Color", "Badge Color",
               "Cursor Guide Color", "Tab Color", "Underline Color")


def detect(data: bytes | str, filename: str | None = None) -> float:
    if filename and filename.lower().endswith(".itermcolors"):
        return 0.98
    if isinstance(data, bytes) and data[:8] == b"bplist00":
        return 0.6  # a binary plist, though not provably an iTerm2 one
    text = decode(data)[:4096]
    if "<plist" not in text:
        return 0.0
    return 0.9 if "Ansi 0 Color" in decode(data) else 0.3


def parse(data: bytes | str, name: str | None = None) -> Palette:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    try:
        document = plistlib.loads(raw)
    except Exception as exc:
        raise ValueError(f"not a readable plist: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("plist root is not a dictionary")

    palette = Palette(name=name, source_format=NAME)
    color_spaces: set[str] = set()

    for key, value in document.items():
        color = _component_color(value, color_spaces)
        if color is None:
            continue
        if m := _RE_ANSI_KEY.match(key):
            index = int(m.group(1))
            if index <= 255:
                palette.set_indexed(index, color)
        elif key in _SCALARS:
            setattr(palette, _SCALARS[key], color)
        elif key in _EXTRA_KEYS:
            palette.extras.setdefault("iterm2", {})[key] = color.hex

    # iTerm2 can store components in Display P3 or a device-calibrated space.
    # We read them as sRGB regardless, so record when that assumption applies.
    off_srgb = {s for s in color_spaces if s.lower() not in {"srgb", ""}}
    if off_srgb:
        palette.extras.setdefault("iterm2", {})["color_space"] = sorted(off_srgb)

    return palette


def _component_color(value: object, color_spaces: set[str]) -> Color | None:
    if not isinstance(value, dict) or "Red Component" not in value:
        return None
    try:
        color = Color.from_floats(
            value["Red Component"],
            value["Green Component"],
            value["Blue Component"],
        )
    except (KeyError, TypeError, ValueError):
        return None
    color_spaces.add(str(value.get("Color Space", "")))
    return color
