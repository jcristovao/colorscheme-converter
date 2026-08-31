"""Windows Terminal output: a scheme object for the `schemes` array."""

from __future__ import annotations

import json

from .._text import single_line
from ..fill import Derivations
from ..palette import ANSI_NAMES, Palette

NAME = "windows-terminal"
EXTENSION = ".json"
BINARY = False

# Windows Terminal says `purple` where the ANSI slot is magenta.
_SLOT_KEYS = tuple("purple" if slot == "magenta" else slot for slot in ANSI_NAMES)

# JSON has no comments, so derived values cannot be annotated here; the CLI
# reports them on stderr instead.
_SCALARS = (
    ("background", "background"),
    ("foreground", "foreground"),
    ("cursorColor", "cursor"),
    ("selectionBackground", "selection_background"),
)


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    scheme: dict[str, str] = {"name": single_line(palette.name) or "cscx"}

    for key, field in _SCALARS:
        if (color := getattr(palette, field)) is not None:
            scheme[key] = color.hex

    for index, key in enumerate(_SLOT_KEYS):
        if (color := palette.ansi[index]) is not None:
            scheme[key] = color.hex
        if (bright := palette.ansi[index + 8]) is not None:
            scheme["bright" + key[0].upper() + key[1:]] = bright.hex

    return json.dumps(scheme, indent=4) + "\n"
