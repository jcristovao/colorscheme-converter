"""Format registry: every parser registers here and is found by name or sniff."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..palette import Palette
from . import (
    alacritty,
    foot,
    ghostty,
    iterm2,
    kde,
    kitty,
    konsole,
    wezterm,
    windows_terminal,
    xresources,
)

__all__ = ["FormatParser", "PARSERS", "READ_ONLY", "get_parser",
           "detect_format", "parse_file"]


@runtime_checkable
class FormatParser(Protocol):
    """What every format module must expose."""

    NAME: str
    ALIASES: tuple[str, ...]
    EXTENSIONS: tuple[str, ...]
    #: True when the source must be handed over as bytes (iTerm2 binary plists).
    BINARY: bool

    def detect(self, data: bytes | str, filename: str | None = None) -> float:
        """Confidence in 0.0-1.0 that `data` is this format."""

    def parse(self, data: bytes | str, name: str | None = None) -> Palette:
        """Read `data` into a palette, or raise `ParseError`."""


class ParseError(ValueError):
    """Raised when a source cannot be read as the requested format."""


#: Formats that can be read but not written back as a terminal scheme. KDE is
#: a desktop target, written through `desktops/`, so it has no entry in
#: `emitters/` -- the two registries are otherwise required to match.
READ_ONLY = frozenset({"kde"})

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
    kde,
)

PARSERS: dict[str, FormatParser] = {}
for _mod in _MODULES:
    PARSERS[_mod.NAME] = _mod  # type: ignore[assignment]
    for _alias in _mod.ALIASES:
        PARSERS[_alias] = _mod  # type: ignore[assignment]


def get_parser(name: str) -> FormatParser:
    """Look up a parser by canonical name or alias."""
    try:
        return PARSERS[name.strip().lower()]
    except KeyError:
        known = sorted({m.NAME for m in _MODULES})
        raise KeyError(f"unknown format {name!r}; known: {', '.join(known)}") from None


def detect_format(data: bytes | str, filename: str | None = None) -> list[tuple[str, float]]:
    """Score every parser against `data`, best first, dropping zero scores."""
    scores = []
    for mod in _MODULES:
        try:
            score = mod.detect(data, filename)
        except Exception:  # a sniffer must never break detection for others
            score = 0.0
        if score > 0:
            scores.append((mod.NAME, score))
    scores.sort(key=lambda pair: (-pair[1], pair[0]))
    return scores


def parse_file(path: str | Path, format: str | None = None) -> Palette:
    """Parse `path`, sniffing the format unless one is given."""
    path = Path(path)
    raw = path.read_bytes()

    if format is not None:
        parser = get_parser(format)
    else:
        ranked = detect_format(raw, path.name)
        if not ranked:
            raise ParseError(
                f"could not identify the format of {path.name}; "
                f"pass --from with one of: {', '.join(sorted({m.NAME for m in _MODULES}))}"
            )
        parser = get_parser(ranked[0][0])

    data = raw if parser.BINARY else raw.decode("utf-8-sig", errors="replace")
    palette = parser.parse(data, name=path.stem)
    return palette
