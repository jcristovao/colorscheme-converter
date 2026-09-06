"""Shared plumbing for the desktop writers.

Two desktops turned out to need the same three things, all of them absent
from a terminal palette and all of them judgement calls rather than lookups:

*A surface ramp.* Every toolkit stacks its surfaces -- content under chrome
under headers -- in steps far finer than an editor's cursorline and
statusline. The ramp is shared; where a desktop puts each step is not.

*An accent.* A terminal scheme has none. Its selection colour is the nearest
thing but usually cannot act as one, because a terminal draws text on top of
its selection and so picks a colour close to the background. It is preferred
and then tested, never trusted.

*A readable foreground for a coloured background.* Both toolkits ask for
text on top of an accent, a red, a green and a yellow, and neither supplies
one.

What is deliberately *not* here is anything a specific toolkit computes for
itself. KDE's shade floor lives in `kde.py` because only KColorScheme has
that cliff; libadwaita's derived standalone colours are simply never written.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..color import Color, contrast_ratio, is_dark, mix
from ..mapping import Mapping

__all__ = [
    "TEXT_CONTRAST", "DIM_CONTRAST", "SURFACE_DEFAULTS",
    "Accent", "pick_accent", "accent_foreground", "make_visible", "clears",
    "contrasting", "ramp",
]

#: WCAG AA for normal text, the same target the editor layer uses.
TEXT_CONTRAST = 4.5

#: Secondary text and focus rings are UI components, which WCAG 2.1 puts at 3:1.
DIM_CONTRAST = 3.0

#: How far each surface steps from the background toward the foreground.
#: Proportioned after Breeze, whose View -> Window -> Button/Header steps are
#: only a few percent apart; Adwaita's are of the same order.
SURFACE_DEFAULTS = {"alternate": 0.045, "window": 0.09, "button": 0.13,
                    "header": 0.13}


@dataclass(frozen=True, slots=True)
class Accent:
    """The desktop accent, and where it came from."""

    color: Color
    source: str


def ramp(background: Color, foreground: Color, mapping: Mapping):
    """A `surface(*keys)` function stepping away from `background`.

    Keys add, so `surface("window", "alternate")` is one step past the window.
    Stepping *away from the background* rather than in a fixed direction is
    what makes this work for light and dark schemes without a special case:
    Breeze Dark sinks its content below the chrome, Breeze Light floats it
    above, and both are "further from the background".
    """
    def surface(*keys: str) -> Color:
        total = sum(mapping.surface(key, SURFACE_DEFAULTS[key]) for key in keys)
        return mix(background, foreground, total)

    return surface


def clears(color: Color, surfaces: tuple[Color, ...], target: float = DIM_CONTRAST) -> bool:
    """Whether `color` is visible against *every* surface."""
    return all(contrast_ratio(color, surface) >= target for surface in surfaces)


def make_visible(
    color: Color,
    surfaces: tuple[Color, ...],
    source: str,
    target: float = DIM_CONTRAST,
) -> Accent:
    """Move a colour until it is visible everywhere, keeping its hue.

    Hue is preserved rather than swapped for a more contrasting one: a gruvbox
    desktop with a cyan focus ring is no longer gruvbox. This is the move the
    editor layer already makes for comments -- keep the intended colour, walk
    it until it clears the bar, and record that it moved.

    The direction is away from the surfaces, which is toward white on a dark
    scheme and toward black on a light one. Worth being careful about: the
    hardest surface is the one nearest the colour in luminance, and on a light
    scheme that is the darkest surface, not the lightest.
    """
    if clears(color, surfaces, target):
        return Accent(color, source)

    # Every surface is a step from the background, so they share its polarity.
    toward = Color(255, 255, 255) if is_dark(surfaces[0]) else Color(0, 0, 0)
    for step in range(1, 101):
        candidate = mix(color, toward, step / 100)
        if clears(candidate, surfaces, target):
            return Accent(candidate, f"{source}, moved to {target}:1 to stay visible")
    return Accent(color, f"{source}, cannot reach {target}:1 on every surface")


def pick_accent(
    palette,
    roles,
    mapping: Mapping,
    surfaces: tuple[Color, ...],
) -> Accent:
    """The one colour a desktop leans on hardest, and a terminal has not got.

    The scheme's selection colour is the nearest thing -- the one place its
    author picked a colour to mean "this is singled out" -- but it only works
    as one when it is actually distinct from the chrome, and usually it is
    not: a terminal renders text *on top* of its selection, so the colour sits
    close to the background. Gruvbox's is #504945 against its own #282828.

    So it is preferred and then tested. What fails falls back to ANSI 4,
    matching base16's base0D and both Breeze's and Adwaita's own blue.
    """
    choice = mapping.kde_accent
    if choice != "selection":
        return make_visible(palette.ansi[choice], surfaces, f"color{choice}")

    selection = palette.selection_background
    if selection is not None and clears(selection, surfaces):
        return make_visible(selection, surfaces, "selection background")

    reason = (
        "color4; the selection background sits too close to the chrome to "
        "carry a focus ring"
        if selection is not None
        else "color4, no selection colour in the source"
    )
    return make_visible(roles["base0D"], surfaces, reason)


def accent_foreground(palette, roles, accent: Accent) -> Color:
    """Text to put on the accent.

    The scheme's own `selection_foreground` is the right answer only when the
    accent really is its `selection_background`. That is easy to get wrong:
    the accent is frequently *not* the selection colour -- it falls back to
    ANSI 4, or gets moved to stay visible -- and a foreground the author chose
    to sit on one colour has no reason to work on another. Gruvbox pairs a
    cream foreground with its #504945 selection, which lands at 2.6:1 on the
    lifted blue that ends up being the accent, where its own background would
    have given 4.2:1.
    """
    if (
        palette.selection_foreground is not None
        and palette.selection_background is not None
        and accent.color == palette.selection_background
    ):
        return palette.selection_foreground
    return contrasting(accent.color, roles["base07"], roles["base00"])


def contrasting(background: Color, light: Color, dark: Color) -> Color:
    """Whichever of two foregrounds reads better on `background`.

    Used wherever a toolkit asks for text on a colour it was given rather than
    one it chose -- an accent, a red, a green -- and supplies no foreground of
    its own.
    """
    if contrast_ratio(light, background) >= contrast_ratio(dark, background):
        return light
    return dark
