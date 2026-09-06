"""Desktop colour scheme writers.

A third spoke, alongside the terminal formats and the editors. Desktops are
write-only for the same reason editors are -- a palette expands into a great
many more values than it can be read back out of -- but they are not editors,
and filing KDE under `editors/` would make `cscx formats` say something untrue
for as long as the file existed.

The protocol is deliberately the same shape as the editors', so `cli._writer`
and the browser wrap all three kinds without any of them knowing about the
others.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..editors.roles import EditorPaletteError
from ..palette import Palette
from . import kde
from .gtk import GTK3, GTK4

__all__ = [
    "DESKTOPS",
    "Desktop",
    "get_desktop",
    "emit_scheme",
    "scheme_warnings",
]


@runtime_checkable
class Desktop(Protocol):
    NAME: str
    EXTENSION: str
    #: Filename template, with `{name}` for the scheme slug.
    FILENAME: str
    BINARY: bool
    #: Where the generated scheme belongs, with `{name}` for the scheme slug.
    INSTALL_PATH: str

    def emit(
        self,
        palette: Palette,
        *,
        terminal_exact: bool = False,
        contrast_target: float | None = None,
    ) -> str: ...

    def warnings(
        self,
        palette: Palette,
        *,
        terminal_exact: bool = False,
        contrast_target: float | None = None,
    ) -> list[str]: ...


_MODULES = (kde, GTK3, GTK4)

DESKTOPS: dict[str, Desktop] = {m.NAME: m for m in _MODULES}  # type: ignore[misc]

_ALIASES = {
    "plasma": "kde",
    "kde-plasma": "kde",
    "colors": "kde",
    # GTK 4 is the modern surface, so the bare names point at it. GTK 3 has to
    # be asked for, which is the right way round: a GTK 3 file does nothing for
    # a libadwaita application.
    "gtk": "gtk4",
    "gnome": "gtk4",
    "libadwaita": "gtk4",
    "adwaita": "gtk4",
    "gtk-4.0": "gtk4",
    "gtk-3.0": "gtk3",
}


def get_desktop(name: str) -> Desktop:
    """Look up a desktop writer by name or alias."""
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    try:
        return DESKTOPS[key]
    except KeyError:
        raise KeyError(
            f"unknown desktop {name!r}; known: {', '.join(sorted(DESKTOPS))}"
        ) from None


def emit_scheme(
    palette: Palette,
    desktop: str,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> str:
    """Render `palette` as a colour scheme for `desktop`."""
    return get_desktop(desktop).emit(
        palette, terminal_exact=terminal_exact, contrast_target=contrast_target
    )


def scheme_warnings(
    palette: Palette,
    desktop: str = "kde",
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> list[str]:
    """Problems worth telling the user about before writing a scheme.

    KDE renders on much harsher terms than a terminal and enforces nothing
    itself, so an unreadable scheme installs and applies exactly like a good
    one. These are the only warning anybody gets.
    """
    try:
        return get_desktop(desktop).warnings(
            palette,
            terminal_exact=terminal_exact,
            contrast_target=contrast_target,
        )
    except EditorPaletteError:
        return []
