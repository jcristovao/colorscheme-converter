"""Vim colorscheme output (`.vim`), with both GUI and cterm colors.

cterm matters here: this is a terminal color scheme converter, and a vim
running in a terminal without truecolor still has to look right. Colors that
are one of the scheme's own ANSI slots emit as indices 0-15, so the terminal
draws them from the very palette this was generated from.
"""

from __future__ import annotations

from ..palette import Palette
from ._common import header_lines, resolve_group, slug
from .groups import CORE
from .roles import CONTRAST_TARGET, Roles, derive

NAME = "vim"
EXTENSION = ".vim"
FILENAME = "{name}.vim"
BINARY = False
#: Where the generated file belongs, mentioned in its own header.
INSTALL_PATH = "~/.vim/colors/{name}.vim"


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float = CONTRAST_TARGET,
) -> str:
    roles = derive(palette, terminal_exact=terminal_exact, contrast_target=contrast_target)
    name = slug(palette.name)

    lines = header_lines(palette, roles, '"')
    lines += [
        '"',
        f'" install as {INSTALL_PATH.format(name=name)}, then `:colorscheme {name}`',
        "",
        "hi clear",
        'if exists("syntax_on")',
        "  syntax reset",
        "endif",
        "",
        f"set background={'dark' if roles.background_is_dark else 'light'}",
        f'let g:colors_name = "{name}"',
        "",
    ]

    for group in CORE:
        resolved = resolve_group(group, roles, palette)
        if resolved.is_empty:
            continue
        if resolved.link:
            lines.append(f"hi! link {resolved.name} {resolved.link}")
        else:
            lines.append(_highlight(resolved))

    lines += ["", *_terminal_colors(palette)]
    return "\n".join(lines) + "\n"


def _highlight(resolved) -> str:
    """One `:highlight` command, with GUI and cterm arguments side by side."""
    style = ",".join(resolved.attrs) if resolved.attrs else "NONE"
    parts = [f"hi {resolved.name}"]

    parts.append(f"guifg={resolved.fg.hex}" if resolved.fg else "guifg=NONE")
    parts.append(f"guibg={resolved.bg.hex}" if resolved.bg else "guibg=NONE")
    if resolved.sp:
        parts.append(f"guisp={resolved.sp.hex}")
    parts.append(f"gui={style}")

    fg_index, bg_index = resolved.cterm(resolved.fg), resolved.cterm(resolved.bg)
    parts.append(f"ctermfg={fg_index if fg_index is not None else 'NONE'}")
    parts.append(f"ctermbg={bg_index if bg_index is not None else 'NONE'}")
    # undercurl and strikethrough have no cterm equivalent in vim.
    cterm = [a for a in resolved.attrs if a in {"bold", "italic", "underline", "reverse"}]
    parts.append(f"cterm={','.join(cterm) if cterm else 'NONE'}")

    return " ".join(parts)


def _terminal_colors(palette: Palette) -> list[str]:
    """Match vim's built-in `:terminal` to the scheme it came from."""
    if any(color is None for color in palette.ansi):
        return []
    values = ", ".join(f"'{color.hex}'" for color in palette.ansi)
    return [
        '" Built-in terminal, so :terminal matches the scheme this came from.',
        "if has('terminal')",
        f"  let g:terminal_ansi_colors = [{values}]",
        "endif",
    ]
