"""Editor theme writers.

Editors are write-only. A terminal scheme has ~20 values and an editor theme
has hundreds of semantic groups, so the mapping from one to the other is
lossy in a way that cannot be run backwards: there is no reading a vim
colorscheme back into 16 ANSI slots. Hence a separate registry from the
terminal emitters, which round-trip.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..palette import Palette
from . import neovim, vim
from .roles import CONTRAST_TARGET, EditorPaletteError

__all__ = [
    "EDITORS",
    "Editor",
    "EditorPaletteError",
    "get_editor",
    "emit_theme",
    "CONTRAST_TARGET",
]


@runtime_checkable
class Editor(Protocol):
    NAME: str
    EXTENSION: str
    BINARY: bool
    #: Where the generated theme belongs, with `{name}` for the scheme slug.
    INSTALL_PATH: str

    def emit(
        self,
        palette: Palette,
        *,
        terminal_exact: bool = False,
        contrast_target: float = CONTRAST_TARGET,
    ) -> str: ...


_MODULES = (vim, neovim)

EDITORS: dict[str, Editor] = {m.NAME: m for m in _MODULES}  # type: ignore[misc]

_ALIASES = {"nvim": "neovim", "vi": "vim"}


def get_editor(name: str) -> Editor:
    """Look up an editor writer by name or alias."""
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    try:
        return EDITORS[key]
    except KeyError:
        raise KeyError(
            f"unknown editor {name!r}; known: {', '.join(sorted(EDITORS))}"
        ) from None


def emit_theme(
    palette: Palette,
    editor: str,
    *,
    terminal_exact: bool = False,
    contrast_target: float = CONTRAST_TARGET,
) -> str:
    """Render `palette` as a theme for `editor`."""
    return get_editor(editor).emit(
        palette, terminal_exact=terminal_exact, contrast_target=contrast_target
    )
