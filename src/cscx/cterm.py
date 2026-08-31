"""Map colors onto terminal color indices for non-truecolor vim sessions.

Indices 0-15 are the terminal's own palette, so a color that *is* one of the
scheme's ANSI slots maps to that index exactly -- the terminal then renders it
from the same palette the editor was generated from. Everything else falls
back to the fixed 6x6x6 cube and grey ramp at 16-255.
"""

from __future__ import annotations

from .color import Color
from .palette import Palette

__all__ = ["cterm_index", "CUBE_LEVELS"]

#: The six intensity steps of the xterm 6x6x6 color cube.
CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def _build_extended() -> list[tuple[int, Color]]:
    """Indices 16-255: the color cube, then the 24-step grey ramp."""
    entries: list[tuple[int, Color]] = []
    index = 16
    for r in CUBE_LEVELS:
        for g in CUBE_LEVELS:
            for b in CUBE_LEVELS:
                entries.append((index, Color(r, g, b)))
                index += 1
    for step in range(24):
        level = 8 + step * 10
        entries.append((index, Color(level, level, level)))
        index += 1
    return entries


_EXTENDED = _build_extended()


def _distance(a: Color, b: Color) -> float:
    """Redmean colour distance -- cheap, and closer to perception than plain RGB."""
    red_mean = (a.r + b.r) / 2
    dr, dg, db = a.r - b.r, a.g - b.g, a.b - b.b
    return (
        (2 + red_mean / 256) * dr * dr
        + 4 * dg * dg
        + (2 + (255 - red_mean) / 256) * db * db
    )


def cterm_index(color: Color, palette: Palette) -> int:
    """The best terminal index for `color`, preferring the scheme's own slots."""
    for index, slot in enumerate(palette.ansi):
        if slot is not None and (slot.r, slot.g, slot.b) == (color.r, color.g, color.b):
            return index
    return min(_EXTENDED, key=lambda entry: _distance(color, entry[1]))[0]
