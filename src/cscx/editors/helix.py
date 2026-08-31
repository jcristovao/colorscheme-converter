"""Helix theme output (`.toml`).

Helix names its colors in a `[palette]` table and refers to them by name from
each scope, so this writer emits the base16 roles as the palette and keeps the
scope table readable -- `"keyword" = "base0E"` rather than a repeated hex
literal. The `[palette]` section is written last because everything after a
TOML table header belongs to that table.

Scope names follow the Helix theme reference; they are close to tree-sitter
captures but not identical, and the `ui.*` tree is Helix's own, so this uses
its own scope table rather than the vim/neovim ones. The roles are shared,
which is the part that matters.
"""

from __future__ import annotations

from ..palette import Palette
from ._common import header_lines, slug
from .groups import HELIX, Group
from .roles import CONTRAST_TARGET, Roles, derive

NAME = "helix"
EXTENSION = ".toml"
BINARY = False
INSTALL_PATH = "~/.config/helix/themes/{name}.toml"

# Helix spells several attributes differently from vim, and expresses
# undercurl as an underline style rather than a modifier.
_MODIFIERS = {
    "bold": "bold",
    "italic": "italic",
    "underline": "underlined",
    "strikethrough": "crossed_out",
    "reverse": "reversed",
    "dim": "dim",
}


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float = CONTRAST_TARGET,
) -> str:
    roles = derive(palette, terminal_exact=terminal_exact, contrast_target=contrast_target)
    name = slug(palette.name)

    lines = header_lines(palette, roles, "#")
    lines += [
        "#",
        f"# install as {INSTALL_PATH.format(name=name)}, then `theme = \"{name}\"`",
        "# in ~/.config/helix/config.toml",
        "",
    ]

    for group in HELIX:
        if rendered := _scope(group, roles):
            lines.append(rendered)

    # Must come last: any bare key after a table header would land inside it.
    lines += ["", "[palette]"]
    for role in sorted(roles.slots):
        lines.append(f'{role} = "{roles.slots[role].hex}"')

    return "\n".join(lines) + "\n"


def _scope(group: Group, roles: Roles) -> str | None:
    """Render one scope line, or `None` when nothing resolved."""
    foreground = roles.resolve_name(group.fg)
    background = roles.resolve_name(group.bg)
    special = roles.resolve_name(group.sp)

    underline = _underline(group, special)
    modifiers = [_MODIFIERS[a] for a in group.attrs if a in _MODIFIERS]

    if not (foreground or background or underline or modifiers):
        return None

    # Helix accepts a bare string as shorthand for a foreground-only scope.
    if foreground and not (background or underline or modifiers):
        return f'"{group.name}" = "{foreground}"'

    parts = []
    if foreground:
        parts.append(f'fg = "{foreground}"')
    if background:
        parts.append(f'bg = "{background}"')
    if underline:
        parts.append(underline)
    if modifiers:
        rendered = ", ".join(f'"{m}"' for m in modifiers)
        parts.append(f"modifiers = [{rendered}]")

    return f'"{group.name}" = {{ {", ".join(parts)} }}'


def _underline(group: Group, special: str | None) -> str | None:
    """Helix carries undercurl as `underline = {{ style = "curl" }}`."""
    if "undercurl" in group.attrs:
        style = "curl"
    elif "underline" in group.attrs and special:
        style = "line"
    else:
        return None

    color = f'color = "{special}", ' if special else ""
    return f'underline = {{ {color}style = "{style}" }}'
