"""iTerm2 .itermcolors output — an XML plist of 0.0-1.0 float components."""

from __future__ import annotations

import plistlib

from ..color import Color
from ..fill import Derivations
from ..palette import Palette

NAME = "iterm2"
EXTENSION = ".itermcolors"
BINARY = True

_SCALARS = (
    ("Background Color", "background"),
    ("Foreground Color", "foreground"),
    ("Cursor Color", "cursor"),
    ("Cursor Text Color", "cursor_text"),
    ("Selection Color", "selection_background"),
    ("Selected Text Color", "selection_foreground"),
)


def emit(palette: Palette, derived: Derivations | None = None) -> bytes:
    document: dict[str, dict[str, object]] = {}

    for index, color in enumerate(palette.ansi):
        if color is not None:
            document[f"Ansi {index} Color"] = _components(color)
    for key, field in _SCALARS:
        if (color := getattr(palette, field)) is not None:
            document[key] = _components(color)

    # iTerm2 stores only the 16 ANSI slots; anything above 15 has no home here.
    return plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=True)


def _components(color: Color) -> dict[str, object]:
    red, green, blue = color.floats
    return {
        "Color Space": "sRGB",
        "Red Component": red,
        "Green Component": green,
        "Blue Component": blue,
        "Alpha Component": 1.0 if color.a is None else color.a,
    }
