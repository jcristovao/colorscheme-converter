"""VS Code theme output (`NAME-color-theme.json`).

Every workbench key emitted here appears in a theme Microsoft ships with VS
Code, which is what proves it is real: VS Code silently ignores keys it does
not recognise, so a typo would quietly do nothing rather than fail loudly.

Unlike the other editors this format carries no provenance header. VS Code's
own themes are plain JSON with no comments, so the derivation notes are
reported on standard error instead of written into the file.
"""

from __future__ import annotations

import json

from .._text import single_line
from ..palette import ANSI_NAMES, Palette
from ._common import slug
from .groups import VSCODE_TOKENS, VSCODE_WORKBENCH
from .roles import CONTRAST_TARGET, Roles, derive

NAME = "vscode"
EXTENSION = ".json"
FILENAME = "{name}-color-theme.json"
BINARY = False
INSTALL_PATH = "~/.vscode/extensions/<extension>/themes/{name}-color-theme.json"

_FONT_STYLES = {
    "bold": "bold",
    "italic": "italic",
    "underline": "underline",
    "strikethrough": "strikethrough",
}


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> str:
    roles = derive(palette, terminal_exact=terminal_exact, contrast_target=contrast_target)

    theme = {
        "name": single_line(palette.name) or slug(palette.name),
        "type": "dark" if roles.background_is_dark else "light",
        "semanticHighlighting": True,
        "colors": _workbench(palette, roles),
        "tokenColors": _tokens(roles),
    }
    return json.dumps(theme, indent=2) + "\n"


def _workbench(palette: Palette, roles: Roles) -> dict[str, str]:
    colors: dict[str, str] = {}
    for entry in VSCODE_WORKBENCH:
        if (color := roles.resolve(entry.role)) is None:
            continue
        colors[entry.key] = (
            color.hex if entry.alpha is None else f"{color.hex}{entry.alpha:02x}"
        )

    # The integrated terminal takes the palette directly -- the one place a
    # VS Code theme and the source scheme can agree exactly.
    for index, slot in enumerate(ANSI_NAMES):
        for offset, prefix in ((0, ""), (8, "Bright")):
            if (color := palette.ansi[index + offset]) is not None:
                key = f"terminal.ansi{prefix}{slot.capitalize()}"
                colors[key] = color.hex

    return colors


def _tokens(roles: Roles) -> list[dict]:
    tokens = []
    for group in VSCODE_TOKENS:
        settings: dict[str, str] = {}
        if (color := roles.resolve(group.fg)) is not None:
            settings["foreground"] = color.hex
        if styles := [_FONT_STYLES[a] for a in group.attrs if a in _FONT_STYLES]:
            settings["fontStyle"] = " ".join(styles)
        if settings:
            tokens.append({"scope": group.name, "settings": settings})
    return tokens
