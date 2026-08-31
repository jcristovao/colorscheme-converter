"""kitty.conf output."""

from __future__ import annotations

from ..fill import Derivations, slot_label
from ..palette import Palette
from ._util import header, note

NAME = "kitty"
EXTENSION = ".conf"
BINARY = False

_SCALARS = (
    ("background", "background"),
    ("foreground", "foreground"),
    ("cursor", "cursor"),
    ("cursor_text_color", "cursor_text"),
    ("selection_background", "selection_background"),
    ("selection_foreground", "selection_foreground"),
)


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    lines = header(palette)
    lines.append("")

    for key, field in _SCALARS:
        if (color := getattr(palette, field)) is not None:
            lines.append(f"{key:<21}{color.hex}{note(derived, field)}")

    lines.append("")
    for index, color in enumerate(palette.ansi):
        if color is None:
            continue
        marker = note(derived, f"color{index}") or f"  # {slot_label(index)}"
        lines.append(f"color{index:<16}{color.hex}{marker}")

    if palette.indexed:
        lines.append("")
        for index in sorted(palette.indexed):
            lines.append(f"color{index:<16}{palette.indexed[index].hex}")

    # Restore kitty's own extras (tab bar, url color) on a same-format trip.
    if extras := palette.extras.get("kitty"):
        lines.append("")
        for key in sorted(extras):
            lines.append(f"{key:<21}{extras[key]}")

    return "\n".join(lines) + "\n"
