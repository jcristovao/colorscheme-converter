"""alacritty TOML output (the 0.13+ format)."""

from __future__ import annotations

from ..fill import Derivations
from ..palette import ANSI_NAMES, Palette
from ._util import header, note

NAME = "alacritty"
EXTENSION = ".toml"
BINARY = False


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    lines = header(palette)

    primary = [
        ("background", "background"),
        ("foreground", "foreground"),
        ("dim_foreground", "dim_foreground"),
        ("bright_foreground", "bright_foreground"),
    ]
    _section(lines, "colors.primary", primary, palette, derived)

    # alacritty calls the glyph under the cursor `text`.
    _section(lines, "colors.cursor",
             [("text", "cursor_text"), ("cursor", "cursor")], palette, derived)
    _section(lines, "colors.selection",
             [("text", "selection_foreground"), ("background", "selection_background")],
             palette, derived)

    for group, offset in (("normal", 0), ("bright", 8)):
        entries = [
            (slot, palette.ansi[offset + i], f"color{offset + i}")
            for i, slot in enumerate(ANSI_NAMES)
        ]
        _color_section(lines, f"colors.{group}", entries, derived)

    _color_section(
        lines,
        "colors.dim",
        [(slot, palette.dim[i], None) for i, slot in enumerate(ANSI_NAMES)],
        derived,
    )

    for index in sorted(palette.indexed):
        lines.append("")
        lines.append("[[colors.indexed_colors]]")
        lines.append(f"index = {index}")
        lines.append(f"color = '{palette.indexed[index].hex}'")

    return "\n".join(lines) + "\n"


def _section(lines, table, fields, palette, derived) -> None:
    present = [(key, getattr(palette, field), field) for key, field in fields]
    _color_section(lines, table, [(k, c, f) for k, c, f in present], derived)


def _color_section(lines, table, entries, derived) -> None:
    """Write `[table]` with its set colors, or nothing if none are set."""
    rows = [(key, color, field) for key, color, field in entries if color is not None]
    if not rows:
        return
    lines.append("")
    lines.append(f"[{table}]")
    width = max(len(key) for key, _, _ in rows)
    for key, color, field in rows:
        marker = note(derived, field) if field else ""
        lines.append(f"{key:<{width}} = '{color.hex}'{marker}")
