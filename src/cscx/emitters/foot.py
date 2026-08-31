"""foot.ini output. foot writes bare `rrggbb`, with no leading hash."""

from __future__ import annotations

from ..fill import Derivations, slot_label
from ..palette import Palette
from ._util import header, note

NAME = "foot"
EXTENSION = ".ini"
BINARY = False


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    lines = header(palette)
    lines.append("")
    lines.append("[colors]")

    if (alpha := (palette.extras.get("foot") or {}).get("alpha")) is not None:
        lines.append(f"alpha={alpha}")
    for key, field in (("background", "background"), ("foreground", "foreground")):
        if (color := getattr(palette, field)) is not None:
            lines.append(f"{key}={color.hex_bare}{note(derived, field)}")

    for offset, prefix in ((0, "regular"), (8, "bright")):
        group = [palette.ansi[offset + i] for i in range(8)]
        if all(c is None for c in group):
            continue
        lines.append("")
        for slot, color in enumerate(group):
            if color is None:
                continue
            index = offset + slot
            marker = note(derived, f"color{index}") or f"  # {slot_label(index)}"
            lines.append(f"{prefix}{slot}={color.hex_bare}{marker}")

    if any(c is not None for c in palette.dim):
        lines.append("")
        for slot, color in enumerate(palette.dim):
            if color is not None:
                lines.append(f"dim{slot}={color.hex_bare}")

    selection = [
        ("selection-foreground", "selection_foreground"),
        ("selection-background", "selection_background"),
    ]
    if any(getattr(palette, field) is not None for _, field in selection):
        lines.append("")
        for key, field in selection:
            if (color := getattr(palette, field)) is not None:
                lines.append(f"{key}={color.hex_bare}{note(derived, field)}")

    # foot spells the cursor as `cursor=<text> <cursor>` inside [colors], and
    # needs both halves; one alone is not expressible. (The older
    # `[cursor] color=` spelling was removed -- foot 1.27 rejects it, though
    # the sample config it ships still shows it.)
    if palette.cursor is not None and palette.cursor_text is not None:
        lines.append(f"cursor={palette.cursor_text.hex_bare} {palette.cursor.hex_bare}")
    elif palette.cursor is not None or palette.cursor_text is not None:
        half = "cursor_text" if palette.cursor is None else "cursor"
        lines.append(f"# cursor omitted: foot needs both halves, {half} is unset")

    if palette.indexed:
        lines.append("")
        for index in sorted(palette.indexed):
            lines.append(f"{index}={palette.indexed[index].hex_bare}")

    return "\n".join(lines) + "\n"
