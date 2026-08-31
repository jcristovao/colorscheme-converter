"""Neovim colorscheme output (`.lua`), covering treesitter, LSP and diagnostics.

Emitted as Lua calling `nvim_set_hl` rather than as `:highlight` commands: it
is what neovim reads natively, and it takes the treesitter capture names
(`@variable.parameter`) and LSP semantic tokens (`@lsp.type.parameter`) that
vimscript cannot express as cleanly.

`termguicolors` is deliberately not set here -- that is the user's setting,
not a colorscheme's business -- but cterm indices are emitted so the theme
degrades sensibly without it.
"""

from __future__ import annotations

from ..palette import Palette
from ._common import header_lines, resolve_group, slug
from .groups import CORE, DIAGNOSTICS, LSP_LINKS, NEOVIM_UI, TREESITTER
from .roles import CONTRAST_TARGET, derive

NAME = "neovim"
EXTENSION = ".lua"
BINARY = False
INSTALL_PATH = "~/.config/nvim/colors/{name}.lua"

_SECTIONS = (
    ("Core groups", CORE),
    ("Interface", NEOVIM_UI),
    ("Treesitter", TREESITTER),
    ("LSP semantic tokens", LSP_LINKS),
    ("Diagnostics", DIAGNOSTICS),
)


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float = CONTRAST_TARGET,
) -> str:
    roles = derive(palette, terminal_exact=terminal_exact, contrast_target=contrast_target)
    name = slug(palette.name)

    lines = header_lines(palette, roles, "--")
    lines += [
        "--",
        f"-- install as {INSTALL_PATH.format(name=name)}, then `:colorscheme {name}`",
        "",
        'vim.cmd("highlight clear")',
        'if vim.fn.exists("syntax_on") == 1 then',
        '  vim.cmd("syntax reset")',
        "end",
        "",
        f'vim.o.background = "{"dark" if roles.background_is_dark else "light"}"',
        f'vim.g.colors_name = "{name}"',
        "",
        "local hl = vim.api.nvim_set_hl",
        "",
    ]

    for title, groups in _SECTIONS:
        lines.append(f"-- {title}")
        for group in groups:
            resolved = resolve_group(group, roles, palette)
            if not resolved.is_empty:
                lines.append(_highlight(resolved))
        lines.append("")

    lines += _terminal_colors(palette)
    return "\n".join(lines) + "\n"


def _highlight(resolved) -> str:
    """One `nvim_set_hl` call."""
    if resolved.link:
        return f'hl(0, "{resolved.name}", {{ link = "{resolved.link}" }})'

    options: list[str] = []
    if resolved.fg:
        options.append(f'fg = "{resolved.fg.hex}"')
    if resolved.bg:
        options.append(f'bg = "{resolved.bg.hex}"')
    if resolved.sp:
        options.append(f'sp = "{resolved.sp.hex}"')
    options += [f"{attribute} = true" for attribute in resolved.attrs]

    if (fg_index := resolved.cterm(resolved.fg)) is not None:
        options.append(f"ctermfg = {fg_index}")
    if (bg_index := resolved.cterm(resolved.bg)) is not None:
        options.append(f"ctermbg = {bg_index}")

    return f'hl(0, "{resolved.name}", {{ {", ".join(options)} }})'


def _terminal_colors(palette: Palette) -> list[str]:
    """Match neovim's built-in `:terminal` to the scheme it came from."""
    if any(color is None for color in palette.ansi):
        return []
    lines = ["-- Built-in terminal, so :terminal matches the scheme this came from."]
    lines += [
        f'vim.g.terminal_color_{index} = "{color.hex}"'
        for index, color in enumerate(palette.ansi)
    ]
    return lines
