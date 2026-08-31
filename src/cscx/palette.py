"""The hub of the hub-and-spoke design: one format-neutral scheme."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .color import Color

__all__ = ["Palette", "ANSI_NAMES", "ansi_index"]

# Slots 0-7 are the normal colors, 8-15 the bright ones. Every terminal format
# agrees on this ordering even when it names the slots differently.
ANSI_NAMES = (
    "black", "red", "green", "yellow",
    "blue", "magenta", "cyan", "white",
)

# Alternate spellings formats use for the same slot.
_ANSI_ALIASES = {
    "purple": "magenta",   # Windows Terminal, Xresources convention
    "brown": "yellow",     # older X11 naming
    "gray": "white",       # rare, but appears in hand-rolled schemes
    "grey": "white",
}


def ansi_index(name: str, *, bright: bool = False) -> int:
    """Map a slot name (`red`, `purple`, ...) to its 0-15 index."""
    key = name.strip().lower()
    key = _ANSI_ALIASES.get(key, key)
    if key not in ANSI_NAMES:
        raise KeyError(f"unknown ANSI slot name: {name!r}")
    return ANSI_NAMES.index(key) + (8 if bright else 0)


@dataclass(slots=True)
class Palette:
    """A terminal color scheme, independent of any one config format.

    Every field is optional: real-world schemes routinely omit cursor or
    selection colors, and a parser must not invent values it did not read.
    Emitters decide for themselves how to fill gaps.
    """

    name: str | None = None
    source_format: str | None = None

    #: 16 ANSI slots; index 0-7 normal, 8-15 bright. `None` means "not specified".
    ansi: list[Color | None] = field(default_factory=lambda: [None] * 16)

    foreground: Color | None = None
    background: Color | None = None

    cursor: Color | None = None
    #: Foreground of the cell *under* the cursor.
    cursor_text: Color | None = None

    selection_background: Color | None = None
    selection_foreground: Color | None = None

    #: Faint/dim variants of slots 0-7, where the format expresses them.
    dim: list[Color | None] = field(default_factory=lambda: [None] * 8)
    dim_foreground: Color | None = None
    bright_foreground: Color | None = None

    #: Extended 256-color slots (index >= 16) for formats that set them.
    indexed: dict[int, Color] = field(default_factory=dict)

    #: Format-specific values worth preserving on round-trip (opacity,
    #: wallpaper path, description, tab-bar colors, ...). Emitters may ignore.
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.ansi) != 16:
            raise ValueError(f"ansi must have 16 slots, got {len(self.ansi)}")
        if len(self.dim) != 8:
            raise ValueError(f"dim must have 8 slots, got {len(self.dim)}")

    # -- slot access -----------------------------------------------------

    @property
    def normal(self) -> list[Color | None]:
        return self.ansi[:8]

    @property
    def bright(self) -> list[Color | None]:
        return self.ansi[8:]

    def set_ansi(self, index: int, color: Color | None) -> None:
        """Set a slot, ignoring `None` so partial sources cannot erase data."""
        if not 0 <= index <= 15:
            raise IndexError(f"ANSI index {index} outside 0-15")
        if color is not None:
            self.ansi[index] = color

    def set_named(self, name: str, color: Color | None, *, bright: bool = False) -> None:
        self.set_ansi(ansi_index(name, bright=bright), color)

    def set_indexed(self, index: int, color: Color | None) -> None:
        """Set any 256-color slot; 0-15 route to `ansi`, the rest to `indexed`."""
        if color is None:
            return
        if 0 <= index <= 15:
            self.ansi[index] = color
        elif 16 <= index <= 255:
            self.indexed[index] = color
        else:
            raise IndexError(f"palette index {index} outside 0-255")

    # -- completeness ----------------------------------------------------

    @property
    def is_complete(self) -> bool:
        """True when all 16 ANSI slots plus fg/bg were found."""
        return not self.missing()

    def missing(self) -> list[str]:
        """Names of the core values this palette lacks, in report order."""
        gaps = [f"color{i}" for i, c in enumerate(self.ansi) if c is None]
        if self.foreground is None:
            gaps.append("foreground")
        if self.background is None:
            gaps.append("background")
        return gaps

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready view; omits everything unset so gaps stay visible."""
        out: dict[str, Any] = {}
        if self.name:
            out["name"] = self.name
        if self.source_format:
            out["source_format"] = self.source_format

        for key in ("foreground", "background", "cursor", "cursor_text",
                    "selection_background", "selection_foreground",
                    "dim_foreground", "bright_foreground"):
            if (color := getattr(self, key)) is not None:
                out[key] = color.hex

        out["ansi"] = [c.hex if c else None for c in self.ansi]
        if any(c is not None for c in self.dim):
            out["dim"] = [c.hex if c else None for c in self.dim]
        if self.indexed:
            out["indexed"] = {str(k): v.hex for k, v in sorted(self.indexed.items())}
        if self.extras:
            out["extras"] = self.extras
        return out
