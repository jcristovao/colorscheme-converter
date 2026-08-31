"""X resources output, as consumed by xrdb, xterm and urxvt."""

from __future__ import annotations

from ..fill import Derivations
from ..palette import Palette
from ._util import header, note_line

NAME = "xresources"
EXTENSION = ".Xresources"
BINARY = False

# X resources has no under-cursor foreground, so `cursor_text` is dropped.
_SCALARS = (
    ("background", "background"),
    ("foreground", "foreground"),
    ("cursorColor", "cursor"),
    ("highlightColor", "selection_background"),
    ("highlightTextColor", "selection_foreground"),
)


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    # `!` is the X resource comment character, not `#`.
    lines = header(palette, comment="!")
    lines.append("")

    for key, field in _SCALARS:
        if (color := getattr(palette, field)) is not None:
            lines.extend(note_line(derived, field, comment="!"))
            lines.append(f"*.{key}:{'':<12}{color.hex}")

    lines.append("")
    for index, color in enumerate(palette.ansi):
        if color is None:
            continue
        lines.extend(note_line(derived, f"color{index}", comment="!"))
        lines.append(f"*.color{index}:{'':<{max(1, 12 - len(str(index)))}}{color.hex}")

    for index in sorted(palette.indexed):
        lines.append(f"*.color{index}: {palette.indexed[index].hex}")

    return "\n".join(lines) + "\n"
