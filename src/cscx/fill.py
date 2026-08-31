"""Derive the values a target format wants but the source never specified.

Off by default: `cscx convert` emits only what it actually read, and lets the
target terminal apply its own defaults. `--fill` turns these conventions on
and records where each derived value came from, so emitters can annotate.
"""

from __future__ import annotations

import copy

from .palette import ANSI_NAMES, Palette

__all__ = ["fill", "Derivations"]

#: field name -> what it was derived from, for emitter comments.
Derivations = dict[str, str]


def fill(palette: Palette) -> tuple[Palette, Derivations]:
    """Return a copy with conventional fallbacks applied, plus their sources.

    Only unset fields are touched; anything the source specified is left
    exactly as read. Order matters: fg/bg are recovered from the ANSI slots
    first, because cursor and selection are then derived from fg/bg.
    """
    filled = copy.deepcopy(palette)
    derived: Derivations = {}

    def take(field: str, value, source: str) -> None:
        if getattr(filled, field) is None and value is not None:
            setattr(filled, field, value)
            derived[field] = source

    # 1. Recover fg/bg from the ANSI slots. Every scheme sets these two even
    #    when it omits everything else, so they anchor the rest.
    take("background", filled.ansi[0], "color0")
    take("foreground", filled.ansi[7], "color7")

    # 2. A missing bright slot conventionally repeats its normal counterpart;
    #    this is what `bold_is_bright no` schemes do explicitly.
    for index in range(8):
        if filled.ansi[index + 8] is None and filled.ansi[index] is not None:
            filled.ansi[index + 8] = filled.ansi[index]
            derived[f"color{index + 8}"] = f"color{index}"

    # 3. The cursor conventionally takes the foreground, with the glyph
    #    beneath it inverted to the background.
    take("cursor", filled.foreground, "foreground")
    take("cursor_text", filled.background, "background")

    # 4. Selection defaults to inverse video in every terminal we target.
    take("selection_background", filled.foreground, "foreground")
    take("selection_foreground", filled.background, "background")

    # 5. konsole and alacritty can hold intense/faint foregrounds; absent a
    #    stated value both conventionally reuse the plain foreground.
    take("bright_foreground", filled.foreground, "foreground")
    take("dim_foreground", filled.foreground, "foreground")

    return filled, derived


def ansi_derivation(derived: Derivations, index: int) -> str | None:
    """The source of ANSI slot `index`, if it was derived."""
    return derived.get(f"color{index}")


def slot_label(index: int) -> str:
    """`color9` -> `bright red`, for readable comments."""
    name = ANSI_NAMES[index % 8]
    return f"bright {name}" if index >= 8 else name
