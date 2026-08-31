"""Apply a palette to the running terminal, temporarily.

Uses OSC escape sequences rather than any one terminal's remote-control
protocol. Every terminal this project targets understands them, nothing has to
be enabled first, and the change is undone by another sequence rather than by
rewriting a file -- which is what makes this safe to do on every keypress while
browsing.

The change is to the terminal's colour registers, not to any config: it lasts
until reset or until the terminal exits.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from .color import Color
from .palette import Palette

__all__ = ["is_supported", "sequences", "apply", "reset", "previewing"]

_ESC = "\x1b"
_ST = f"{_ESC}\\"

#: OSC number for each scalar. 4 is the indexed palette; the rest are named.
_FOREGROUND, _BACKGROUND, _CURSOR, _SELECTION = 10, 11, 12, 17

#: Their matching reset codes. There is no reset for selection, so restoring it
#: is left to the full palette reset.
_RESETS = (104, 110, 111, 112)


def _spec(color: Color) -> str:
    """X11 `rgb:` notation, which every terminal accepts for OSC."""
    return f"rgb:{color.r:02x}/{color.g:02x}/{color.b:02x}"


def _wrap(payload: str) -> str:
    """Wrap for tmux, which otherwise swallows OSC instead of forwarding it."""
    if not os.environ.get("TMUX"):
        return payload
    inner = payload.replace(_ESC, _ESC * 2)
    return f"{_ESC}Ptmux;{inner}{_ST}"


def sequences(palette: Palette) -> str:
    """The escape sequences that would set `palette`, as one string."""
    parts = []
    for index, color in enumerate(palette.ansi):
        if color is not None:
            parts.append(f"{_ESC}]4;{index};{_spec(color)}{_ST}")
    for index, color in palette.indexed.items():
        parts.append(f"{_ESC}]4;{index};{_spec(color)}{_ST}")

    for osc, color in (
        (_FOREGROUND, palette.foreground),
        (_BACKGROUND, palette.background),
        (_CURSOR, palette.cursor),
        (_SELECTION, palette.selection_background),
    ):
        if color is not None:
            parts.append(f"{_ESC}]{osc};{_spec(color)}{_ST}")

    return _wrap("".join(parts))


def reset_sequences() -> str:
    """The sequences that restore the terminal's own configured colors."""
    return _wrap("".join(f"{_ESC}]{code}{_ST}" for code in _RESETS))


def is_supported() -> bool:
    """Whether there is a terminal here that could receive the sequences."""
    if os.environ.get("TERM", "") in {"", "dumb"}:
        return False
    try:
        return os.access("/dev/tty", os.W_OK)
    except OSError:
        return False


def _write(payload: str) -> bool:
    """Write straight to the terminal, bypassing any redirection.

    Going to /dev/tty rather than stdout matters twice over: it works when
    output is piped, and it does not disturb a TUI that owns stdout.
    """
    try:
        with Path("/dev/tty").open("w") as tty:
            tty.write(payload)
            tty.flush()
        return True
    except OSError:
        return False


def apply(palette: Palette) -> bool:
    """Set the running terminal's colors. Returns False if it could not."""
    return _write(sequences(palette))


def reset() -> bool:
    """Restore the terminal's configured colors."""
    return _write(reset_sequences())


@contextmanager
def previewing(palette: Palette):
    """Apply `palette` for the duration of the block, then restore.

    Resetting in a `finally` matters: leaving someone's terminal recoloured
    because of an exception would be a rude way to fail.
    """
    applied = apply(palette)
    try:
        yield applied
    finally:
        if applied:
            reset()
