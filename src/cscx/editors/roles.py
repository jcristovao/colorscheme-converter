"""Map a terminal palette onto base16's sixteen semantic roles.

This is the opinionated layer. A terminal scheme is ~20 values; an editor
theme is hundreds of highlight groups, so something has to decide that "green"
means "string". base16 is the established answer, and using its role names
means the group tables here read the same as every base16 template in the
wild.

The one thing base16 has that a terminal palette does not is the greyscale
ramp base01-base04: statusline, cursorline, line numbers and comments. Those
are synthesised, unless `terminal_exact` forbids it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..color import Color, contrast_ratio, is_dark, mix
from ..palette import Palette

__all__ = [
    "Roles", "derive", "EditorPaletteError",
    "CONTRAST_TARGET", "COMMENT_BLEND_FLOOR", "COMMENT_BLEND_CEILING",
]

#: WCAG AA for normal text. Comments and line numbers are normal text, and an
#: unreadable comment colour is the classic failure of a generated theme.
CONTRAST_TARGET = 4.5

#: How far base03 may travel from the background toward the foreground. The
#: ceiling matters: some schemes (solarized light especially) have so little
#: room between background and foreground that hitting 4.5:1 would put
#: comments almost exactly on top of normal text, trading one unreadable
#: result for another. Better to stop short, and say so.
COMMENT_BLEND_FLOOR = 0.45
COMMENT_BLEND_CEILING = 0.85

# Where each accent role comes from. base16's palette is ordered by meaning,
# not by hue, so this mapping is what ties "ANSI 4 is blue" to "functions".
_ACCENTS = {
    "base08": 1,   # variables, diff deleted        -> red
    "base0A": 3,   # classes, types, search         -> yellow
    "base0B": 2,   # strings, diff added            -> green
    "base0C": 6,   # escapes, regex, support        -> cyan
    "base0D": 4,   # functions, methods, headings   -> blue
    "base0E": 5,   # keywords, storage              -> magenta
}


class EditorPaletteError(ValueError):
    """Raised when a palette lacks what an editor theme needs."""


@dataclass
class Roles:
    """base16 roles plus the terminal values worth carrying through."""

    slots: dict[str, Color]
    #: role -> how it was obtained, for the generated file's header comment.
    provenance: dict[str, str] = field(default_factory=dict)
    background_is_dark: bool = True
    terminal_exact: bool = False
    #: Problems worth telling the user about, but not worth failing over.
    warnings: list[str] = field(default_factory=list)

    def __getitem__(self, name: str) -> Color:
        return self.slots[name]

    def resolve(self, chain: str | None) -> Color | None:
        """Resolve a `"selection_bg|base02"` fallback chain to the first hit."""
        if not chain:
            return None
        for name in chain.split("|"):
            if (color := self.slots.get(name)) is not None:
                return color
        return None


def derive(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float = CONTRAST_TARGET,
) -> Roles:
    """Build the sixteen base16 roles from a terminal palette."""
    if gaps := palette.missing():
        # The eight normal hues are the floor: an absent hue has nothing to be
        # derived from, so --fill cannot help and saying otherwise misleads.
        normals = [gap for gap in gaps if gap in {f"color{i}" for i in range(8)}]
        if normals:
            raise EditorPaletteError(
                f"an editor theme needs all eight normal ANSI colors, and the "
                f"source does not define {', '.join(normals)}; an absent hue "
                f"cannot be derived from the others"
            )
        raise EditorPaletteError(
            f"an editor theme needs a complete palette; missing {', '.join(gaps)}. "
            f"Pass --fill to derive them."
        )

    background, foreground = palette.background, palette.foreground
    assert background is not None and foreground is not None  # missing() checked
    dark = is_dark(background)

    slots: dict[str, Color] = {"base00": background, "base05": foreground}
    provenance: dict[str, str] = {"base00": "background", "base05": "foreground"}
    warnings: list[str] = []

    if terminal_exact:
        _exact_ramp(palette, slots, provenance, warnings)
    else:
        _derived_ramp(palette, slots, provenance, dark)

    _comments(slots, provenance, warnings, terminal_exact, contrast_target)
    _accents(palette, slots, provenance, terminal_exact)

    # Carry the terminal's own cursor and selection through, so the editor
    # agrees with the terminal it was generated from wherever it can.
    for role, source in (
        ("cursor", palette.cursor),
        ("cursor_text", palette.cursor_text),
        ("selection_bg", palette.selection_background),
        ("selection_fg", palette.selection_foreground),
    ):
        if source is not None:
            slots[role] = source
            provenance[role] = "terminal"

    return Roles(
        slots=slots,
        provenance=provenance,
        background_is_dark=dark,
        terminal_exact=terminal_exact,
        warnings=warnings,
    )


def _derived_ramp(palette, slots, provenance, dark) -> None:
    """Synthesise the UI shades by stepping from background toward foreground."""
    background, foreground = slots["base00"], slots["base05"]

    for role, t in (("base01", 0.10), ("base02", 0.22), ("base04", 0.72)):
        slots[role] = mix(background, foreground, t)
        provenance[role] = f"{int(t * 100)}% background -> foreground"

    # base06 and base07 continue past the foreground, toward whichever
    # extreme the theme is heading for.
    extreme = Color(255, 255, 255) if dark else Color(0, 0, 0)
    for role, t in (("base06", 0.25), ("base07", 0.50)):
        slots[role] = mix(foreground, extreme, t)
        provenance[role] = f"{int(t * 100)}% foreground -> {'white' if dark else 'black'}"


def _exact_ramp(palette, slots, provenance, warnings) -> None:
    """Use only palette colors, at the cost of a flatter UI."""
    for role, index in (
        ("base01", 0), ("base02", 8), ("base04", 7), ("base06", 7), ("base07", 15),
    ):
        slots[role] = palette.ansi[index]
        provenance[role] = f"color{index}"

    if slots["base01"] == slots["base00"]:
        warnings.append(
            "color0 equals the background, so cursorline and statusline will be "
            "invisible; drop --terminal-exact to derive a distinct shade"
        )


def _comments(slots, provenance, warnings, terminal_exact, target) -> None:
    """Pick base03 -- comments and line numbers -- and prove it is readable."""
    background = slots["base00"]

    if terminal_exact:
        slots["base03"] = slots["base02"]
        provenance["base03"] = "color8"
        ratio = contrast_ratio(slots["base03"], background)
        if ratio < target:
            warnings.append(
                f"comments sit at {ratio:.1f}:1 against the background, below the "
                f"{target}:1 readability target; color8 is what --terminal-exact allows"
            )
        return

    # Step away from the background until comments clear the target, so a
    # low-contrast source scheme cannot produce unreadable comments.
    foreground = slots["base05"]
    floor = int(COMMENT_BLEND_FLOOR * 100)
    ceiling = int(COMMENT_BLEND_CEILING * 100)

    for step in range(floor, ceiling + 1):
        candidate = mix(background, foreground, step / 100)
        if contrast_ratio(candidate, background) >= target:
            slots["base03"] = candidate
            provenance["base03"] = (
                f"{step}% background -> foreground, {target}:1 contrast"
            )
            return

    # The scheme has too little room between background and foreground. Stop
    # at the ceiling rather than collapsing comments onto normal text.
    capped = mix(background, foreground, COMMENT_BLEND_CEILING)
    slots["base03"] = capped
    provenance["base03"] = f"{ceiling}% background -> foreground, contrast-capped"
    warnings.append(
        f"comments reach {contrast_ratio(capped, background):.1f}:1 against the "
        f"background, short of {target}:1; going further would make them "
        f"indistinguishable from normal text in this low-contrast scheme"
    )


def _accents(palette, slots, provenance, terminal_exact) -> None:
    """Assign the eight accent roles from the ANSI hues."""
    for role, index in _ACCENTS.items():
        slots[role] = palette.ansi[index]
        provenance[role] = f"color{index}"

    # base09 (constants, numbers) wants orange, and base0F (deprecated) brown.
    # No terminal slot holds either, so exact mode borrows the bright variants
    # and derived mode blends the red and yellow that bracket them.
    if terminal_exact:
        slots["base09"] = palette.ansi[9]
        provenance["base09"] = "color9"
        slots["base0F"] = palette.ansi[13]
        provenance["base0F"] = "color13"
    else:
        red, yellow = palette.ansi[1], palette.ansi[3]
        slots["base09"] = mix(red, yellow, 0.50)
        provenance["base09"] = "50% color1 -> color3"
        slots["base0F"] = mix(red, yellow, 0.25)
        provenance["base0F"] = "25% color1 -> color3"
