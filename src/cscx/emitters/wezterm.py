"""wezterm TOML colour scheme output."""

from __future__ import annotations

from .._text import toml_string
from ..fill import Derivations
from ..palette import Palette
from ._util import header, note

NAME = "wezterm"
EXTENSION = ".toml"
BINARY = False

_SCALARS = (
    ("background", "background"),
    ("foreground", "foreground"),
    ("cursor_bg", "cursor"),
    ("cursor_fg", "cursor_text"),
    ("selection_bg", "selection_background"),
    ("selection_fg", "selection_foreground"),
)


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    lines = header(palette)

    if palette.name:
        lines.append("")
        lines.append("[metadata]")
        lines.append(f"name = {toml_string(palette.name)}")

    lines.append("")
    lines.append("[colors]")
    for key, field in _SCALARS:
        if (color := getattr(palette, field)) is not None:
            lines.append(f'{key} = "{color.hex}"{note(derived, field)}')

    # wezterm's `ansi` and `brights` are fixed-length arrays; a partial one is
    # not expressible, so an incomplete group is reported rather than padded.
    for key, offset in (("ansi", 0), ("brights", 8)):
        group = palette.ansi[offset:offset + 8]
        if all(c is not None for c in group):
            values = ", ".join(f'"{c.hex}"' for c in group)
            lines.append(f"{key} = [{values}]")
        elif any(c is not None for c in group):
            missing = [f"color{offset + i}" for i, c in enumerate(group) if c is None]
            lines.append(f"# {key} omitted: wezterm needs all 8; missing {', '.join(missing)}")

    if palette.indexed:
        lines.append("")
        lines.append("[colors.indexed]")
        for index in sorted(palette.indexed):
            lines.append(f'{index} = "{palette.indexed[index].hex}"')

    return "\n".join(lines) + "\n"
