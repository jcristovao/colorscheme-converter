"""ghostty config output."""

from __future__ import annotations

from ..fill import Derivations
from ..palette import Palette
from ._util import header, note_line

NAME = "ghostty"
EXTENSION = ""
BINARY = False

_SCALARS = (
    ("background", "background"),
    ("foreground", "foreground"),
    ("cursor-color", "cursor"),
    ("cursor-text", "cursor_text"),
    ("selection-background", "selection_background"),
    ("selection-foreground", "selection_foreground"),
)


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    lines = header(palette)
    lines.append("")

    for index, color in enumerate(palette.ansi):
        if color is None:
            continue
        lines.extend(note_line(derived, f"color{index}"))
        lines.append(f"palette = {index}={color.hex}")
    for index in sorted(palette.indexed):
        lines.append(f"palette = {index}={palette.indexed[index].hex}")

    lines.append("")
    for key, field in _SCALARS:
        if (color := getattr(palette, field)) is not None:
            lines.extend(note_line(derived, field))
            lines.append(f"{key} = {color.hex}")

    extras = palette.extras.get("ghostty") or {}
    if (opacity := extras.get("background-opacity")) is not None:
        lines.append(f"background-opacity = {opacity}")

    return "\n".join(lines) + "\n"
