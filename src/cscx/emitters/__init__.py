"""Emitter registry: the spoke side of the hub-and-spoke design."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..fill import Derivations
from ..palette import Palette
from . import (
    alacritty,
    foot,
    ghostty,
    iterm2,
    kitty,
    konsole,
    wezterm,
    windows_terminal,
    xresources,
)

__all__ = ["Emitter", "EMITTERS", "get_emitter", "emit"]


@runtime_checkable
class Emitter(Protocol):
    """What every emitter module must expose."""

    NAME: str
    #: Suggested extension when writing to a file, `""` for extensionless.
    EXTENSION: str
    #: True when `emit` returns bytes (iTerm2 plists).
    BINARY: bool

    def emit(self, palette: Palette, derived: Derivations | None = None) -> str | bytes:
        """Render `palette` in this format."""


_MODULES = (
    kitty,
    ghostty,
    alacritty,
    konsole,
    iterm2,
    foot,
    wezterm,
    windows_terminal,
    xresources,
)

EMITTERS: dict[str, Emitter] = {m.NAME: m for m in _MODULES}  # type: ignore[misc]

# Accept the same aliases the parsers do, so --from and --to stay symmetric.
_ALIASES = {
    "kitty.conf": "kitty",
    "alacritty-toml": "alacritty",
    "alacritty-yaml": "alacritty",
    "alacritty-yml": "alacritty",
    "kterminal": "konsole",
    "iterm": "iterm2",
    "itermcolors": "iterm2",
    "foot.ini": "foot",
    "windowsterminal": "windows-terminal",
    "wt": "windows-terminal",
    "xdefaults": "xresources",
    "xrdb": "xresources",
}


def get_emitter(name: str) -> Emitter:
    """Look up an emitter by canonical name or alias."""
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    try:
        return EMITTERS[key]
    except KeyError:
        raise KeyError(
            f"unknown output format {name!r}; known: {', '.join(sorted(EMITTERS))}"
        ) from None


def emit(palette: Palette, format: str, derived: Derivations | None = None) -> str | bytes:
    """Render `palette` as `format`."""
    return get_emitter(format).emit(palette, derived)
