"""Write a terminal palette as a KDE Plasma colour scheme.

A `.colors` file looks enormous -- seven colour sets of twelve keys each,
plus the window manager, the state effects and the metadata -- but it has
very few degrees of freedom, and they line up almost exactly with the base16
roles the editor layer already derives:

    ForegroundNegative  base08   ANSI 1, red
    ForegroundNeutral   base0A   ANSI 3, yellow
    ForegroundPositive  base0B   ANSI 2, green
    ForegroundLink      base0D   ANSI 4, blue
    ForegroundVisited   base0E   ANSI 5, magenta
    ForegroundNormal    base05
    ForegroundInactive  base04

So `roles.derive()` is reused wholesale. What is added here is the *surface
ramp*: Plasma stacks View under Window under Button and Header, and its steps
are far finer than an editor's cursorline and statusline. `base01` at 10% and
`base02` at 22% are both too coarse and too far apart, so KDE gets its own
four steps, tunable under `[kde]` in the mapping file.

Two things Plasma does at runtime shape everything below.

`KColorScheme::shade()` generates every bevel, frame and separator from a
set's background, and it has degenerate branches under luma 0.006 and over
0.93 where the Light/Midlight/Mid/Dark/Shadow family collapses onto itself.
A `#000000` terminal background -- common -- would therefore produce a
desktop with no visible frames at all. The derived surfaces are held inside a
safe band for that reason; `base00` never is, because altering what the source
actually stated is not this program's business. A background outside the band
is reported instead.

And the six background roles that are *not* in the file -- Active, Link,
Visited, Negative, Neutral, Positive -- are computed by Plasma as
`tint(BackgroundNormal, Foreground<Role>)`. The tinted banners in
KMessageWidget come from the foregrounds written here, so there is nothing to
emit for them and no way to override them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .._text import single_line
from ..color import Color, contrast_ratio, is_dark, luminance, mix
from ..editors._common import slug
from ..editors.roles import Roles, derive
from ..mapping import Mapping, load as load_mapping
from ..palette import Palette

NAME = "kde"
EXTENSION = ".colors"
FILENAME = "{name}.colors"
BINARY = False
INSTALL_PATH = "~/.local/share/color-schemes/{name}.colors"
#: Plasma reads a scheme by its file stem, so the name in `[General]` and the
#: filename cannot disagree.
NAME_IS_FILENAME = True

__all__ = ["emit", "warnings", "NAME", "EXTENSION", "FILENAME", "INSTALL_PATH"]


# -- what Plasma degenerates on -------------------------------------------

#: Where `KColorScheme::shade()` switches to its dark degenerate branch, in
#: which Light and Midlight collapse onto Mid, Dark and Shadow -- so every
#: frame, bevel and separator drawn from that background disappears.
#:
#: Only the dark branch is guarded. There is a light one too, at luma 0.93,
#: but Breeze Light ships a pure white view background and lives in it quite
#: happily: when the background is light it is the *dark* shades that draw the
#: frames, and those still separate. Holding light surfaces down to 0.93 would
#: make generated schemes duller than the one KDE ships, for no gain.
SHADE_FLOOR = 0.006

#: Where derived surfaces are held: a little inside the branch, so rounding
#: cannot drop one back over the edge. Breeze Dark's own view background sits
#: at 0.0079, which is the same judgement call made by hand.
LUMA_FLOOR = 0.010

#: WCAG minimums. Normal text is the same target the editor layer uses;
#: secondary text and focus rings are UI components, which WCAG 2.1 puts at 3:1.
TEXT_CONTRAST = 4.5
DIM_CONTRAST = 3.0

#: Where the semantic hues are put when they land on the highlight. The
#: accent is usually one of them -- ANSI 4 -- so ForegroundLink on the
#: selection is otherwise the same colour as its own background, at 1.0:1.
#: Breeze shifts four of its hues for exactly this reason, reaching 1.5 to
#: 2.7:1; this aims a little past the best of those.
SELECTION_HUE_CONTRAST = 2.5

#: Selected text gets its own, much lower bar. Every scheme KDE ships is around
#: 2.4:1 here -- Breeze Dark 2.43, Breeze Light 2.49, Oxygen 2.53 -- because a
#: saturated highlight cannot carry high-contrast text in either direction. A
#: gate upstream fails in every one of its own schemes is noise, so this one
#: catches only genuinely invisible selections.
SELECTION_CONTRAST = 2.0

#: Breeze's own `[ColorEffects:Disabled]`, which is what turns ForegroundNormal
#: into disabled text: fade 65% toward the background, then darken by 10%.
DISABLED_FADE = 0.65
DISABLED_CONTRAST = 2.0

#: The twelve keys every colour set carries, in the order KConfig writes them.
KEYS = (
    "BackgroundAlternate",
    "BackgroundNormal",
    "DecorationFocus",
    "DecorationHover",
    "ForegroundActive",
    "ForegroundInactive",
    "ForegroundLink",
    "ForegroundNegative",
    "ForegroundNeutral",
    "ForegroundNormal",
    "ForegroundPositive",
    "ForegroundVisited",
)

#: The seven sets, in the order they are written. Every one is emitted in
#: full: a missing key falls back to a hardcoded Breeze *Light* constant, which
#: is how a dark scheme ends up with a blinding white tooltip.
SETS = (
    "Colors:Button",
    "Colors:Complementary",
    "Colors:Header",
    "Colors:Header][Inactive",
    "Colors:Selection",
    "Colors:Tooltip",
    "Colors:View",
    "Colors:Window",
)

#: Structural rather than palette: these describe how Plasma should treat the
#: colours, not what they are. Breeze's values, verbatim.
EFFECTS = """[ColorEffects:Disabled]
Color=56,56,56
ColorAmount=0
ColorEffect=0
ContrastAmount=0.65
ContrastEffect=1
IntensityAmount=0.1
IntensityEffect=2

[ColorEffects:Inactive]
ChangeSelectionColor=true
Color=112,111,110
ColorAmount=0.025
ColorEffect=2
ContrastAmount=0.1
ContrastEffect=2
Enable=false
IntensityAmount=0
IntensityEffect=0"""


class Scheme:
    """The resolved colours, before expansion into eighty-four keys."""

    __slots__ = ("sets", "wm", "dark", "provenance", "warnings")

    def __init__(self) -> None:
        self.sets: dict[str, dict[str, Color]] = {}
        self.wm: dict[str, Color] = {}
        self.dark = True
        self.provenance: list[tuple[str, Color, str]] = []
        self.warnings: list[str] = []


@dataclass(frozen=True, slots=True)
class _Accent:
    """The desktop accent, and where it came from."""

    color: Color
    source: str


# -- the safe band --------------------------------------------------------


def in_band(color: Color) -> bool:
    """Whether Plasma's shade generator stays out of its degenerate branch."""
    return luminance(color) >= SHADE_FLOOR


def _hold_in_band(color: Color) -> Color:
    """Lift a *derived* surface clear of the luma Plasma stops shading at.

    Stepping toward white rather than clamping a channel, so the hue survives
    the move: a near-black blue surface should come back as a slightly less
    black blue, not as grey.
    """
    if luminance(color) >= LUMA_FLOOR:
        return color

    candidate = color
    for step in range(1, 61):
        candidate = mix(color, Color(255, 255, 255), step / 200)
        if luminance(candidate) >= LUMA_FLOOR:
            break
    return candidate


# -- resolving the palette ------------------------------------------------


def _accent(
    palette: Palette, roles: Roles, mapping: Mapping, surfaces: tuple[Color, ...]
) -> _Accent:
    """The one colour Plasma leans on hardest.

    A terminal scheme has no accent. Its selection colour is the closest
    thing -- the one place the author picked a colour to mean "this is
    singled out" -- but it only works as one when it is actually distinct
    from the chrome, and usually it is not: a terminal renders text *on top*
    of its selection, so the colour is chosen to sit close to the background.
    Gruvbox's is #504945, barely off its own #282828.

    So the selection colour is preferred and then tested, rather than
    trusted. What fails falls back to ANSI 4, matching base16's base0D and
    Breeze's own blue.
    """
    choice = mapping.kde_accent
    if choice != "selection":
        return _usable(palette.ansi[choice], surfaces, f"color{choice}")

    selection = palette.selection_background
    if selection is not None and _clears(selection, surfaces):
        return _usable(selection, surfaces, "selection background")

    reason = (
        "color4; the selection background sits too close to the chrome to "
        "carry a focus ring"
        if selection is not None
        else "color4, no selection colour in the source"
    )
    return _usable(roles["base0D"], surfaces, reason)


def _clears(color: Color, surfaces: tuple[Color, ...]) -> bool:
    """Whether a focus ring in this colour is visible on *every* surface."""
    return all(contrast_ratio(color, surface) >= DIM_CONTRAST for surface in surfaces)


def _usable(color: Color, surfaces: tuple[Color, ...], source: str) -> _Accent:
    """Move an accent until a focus ring drawn in it is visible everywhere.

    Hue is preserved rather than swapped for a more contrasting one: a gruvbox
    desktop with a cyan focus ring is no longer gruvbox. This is the same move
    the editor layer makes for comments -- keep the intended colour, walk it
    until it clears the bar, and record that it moved.

    The direction is away from the surfaces, which is *toward* white on a dark
    scheme and toward black on a light one. Worth being careful about: the
    hardest surface is the one closest to the accent in luminance, and on a
    light scheme that is the darkest surface, not the lightest. Breeze Light
    gets this wrong -- its focus ring is 1.9:1 on its own header.
    """
    if _clears(color, surfaces):
        return _Accent(color, source)

    # Every surface is a step from the background, so they share its polarity.
    toward = Color(255, 255, 255) if is_dark(surfaces[0]) else Color(0, 0, 0)
    for step in range(1, 101):
        candidate = mix(color, toward, step / 100)
        if _clears(candidate, surfaces):
            return _Accent(
                candidate, f"{source}, moved to {DIM_CONTRAST}:1 for the focus ring"
            )
    return _Accent(color, f"{source}, cannot reach {DIM_CONTRAST}:1 on every surface")


def _hover(palette: Palette, mapping: Mapping, accent: _Accent) -> _Accent:
    """The hover decoration.

    Breeze sets this equal to DecorationFocus, but Oxygen did not, and ANSI 6
    is otherwise the one hue with nowhere to go in a KDE scheme -- there are
    five semantic foregrounds and cyan is not one of them. Giving it this job
    is the only way the scheme's cyan reaches the desktop at all.
    """
    choice = mapping.kde_hover
    if choice == "accent":
        return _Accent(accent.color, f"accent ({accent.source})")
    return _Accent(palette.ansi[choice], f"color{choice}")


def _selection_foreground(palette: Palette, roles: Roles, accent: Color) -> Color:
    """Text on the accent, which is the one place contrast can be chosen."""
    if palette.selection_foreground is not None:
        return palette.selection_foreground
    light, dark = roles["base07"], roles["base00"]
    if contrast_ratio(light, accent) >= contrast_ratio(dark, accent):
        return light
    return dark


#: The foregrounds that land on the highlight and need room made for them.
#: ForegroundNormal is chosen against the accent already, and DecorationFocus
#: is deliberately equal to the background, as it is in Breeze.
_SELECTION_HUES = (
    "ForegroundLink", "ForegroundVisited", "ForegroundNegative",
    "ForegroundNeutral", "ForegroundPositive", "ForegroundInactive",
)


def _selection_hues(common: dict, accent: Color) -> dict[str, Color]:
    """Make the semantic hues readable once they sit on the highlight.

    The accent is usually ANSI 4, and ForegroundLink *is* ANSI 4, so carrying
    the hues over unchanged puts a link on a background of its own colour --
    1.0:1, perfectly invisible. Breeze solves this by hand, darkening its
    negative, neutral and positive and swapping its link to yellow.

    Done here by moving each hue toward whichever extreme the accent is
    furthest from, which keeps the hue recognisable where a swap would not.
    A mid-luminance accent has more room below it than above, so this usually
    darkens -- the same direction Breeze chose.

    Note what this does *not* reach. `QPalette` carries a single `Link` role,
    taken from `Colors:View`, so a plain Qt widget drawing a link inside a
    selected row uses the view's link colour whatever this set says; only
    KColorScheme-aware code (Kirigami, KDE's own applications) reads the
    values written here. That collision is upstream and Breeze has it too --
    its view link lands at 1.22:1 on its own highlight. Fixing it would mean
    pulling the accent away from ANSI 4, which costs the scheme its character
    for a narrow case, so it is left alone and written down instead.
    """
    toward = (
        Color(0, 0, 0)
        if contrast_ratio(Color(0, 0, 0), accent) >= contrast_ratio(Color(255, 255, 255), accent)
        else Color(255, 255, 255)
    )

    shifted: dict[str, Color] = {}
    for key in _SELECTION_HUES:
        color = common[key]
        best = color
        for step in range(0, 101):
            candidate = mix(color, toward, step / 100)
            best = candidate
            if contrast_ratio(candidate, accent) >= SELECTION_HUE_CONTRAST:
                break
        shifted[key] = best
    return shifted


def resolve(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
    mapping: Mapping | None = None,
) -> Scheme:
    """Work out every colour the file will carry."""
    mapping = mapping or load_mapping()
    roles = derive(
        palette,
        terminal_exact=terminal_exact,
        contrast_target=contrast_target,
        mapping=mapping,
    )

    scheme = Scheme()
    scheme.dark = roles.background_is_dark
    scheme.warnings = list(roles.warnings)

    background, foreground = roles["base00"], roles["base05"]

    # Every derived surface steps from here rather than from the background
    # itself. Lifting each one separately would pile them all onto the floor
    # for a near-black scheme -- window, button and header would come out the
    # same colour and the elevation Plasma needs would be gone. Lifting the
    # base instead keeps the spacing and costs only the surfaces, never the
    # background the source actually stated.
    ramp_base = _hold_in_band(background)

    def surface(*keys: str) -> Color:
        """A derived surface, stepped away from the background."""
        total = sum(mapping.surface(key, _SURFACE_DEFAULTS[key]) for key in keys)
        return mix(ramp_base, foreground, total)

    alternate = surface("alternate")
    window = surface("window")
    window_alt = surface("window", "alternate")
    button = surface("button")
    header = surface("header")

    # The accent has to carry a focus ring on every surface, so it is tested
    # against all of them rather than against a representative one.
    accent = _accent(palette, roles, mapping, (background, window, button, header))
    hover = _hover(palette, mapping, accent)

    # Shared by every set but Selection and Complementary. Plasma expects the
    # accent to be the same everywhere -- Breeze repeats it in all seven.
    common = {
        "DecorationFocus": accent.color,
        "DecorationHover": hover.color,
        "ForegroundActive": accent.color,
        "ForegroundInactive": roles["base04"],
        "ForegroundLink": roles["base0D"],
        "ForegroundNegative": roles["base08"],
        "ForegroundNeutral": roles["base0A"],
        "ForegroundNormal": foreground,
        "ForegroundPositive": roles["base0B"],
        "ForegroundVisited": roles["base0E"],
    }

    scheme.sets["Colors:View"] = {
        **common, "BackgroundNormal": background, "BackgroundAlternate": alternate,
    }
    scheme.sets["Colors:Window"] = {
        **common, "BackgroundNormal": window, "BackgroundAlternate": window_alt,
    }
    scheme.sets["Colors:Tooltip"] = {
        **common, "BackgroundNormal": window, "BackgroundAlternate": window_alt,
    }
    # Breeze puts an accent tint in the button set's alternate, where it reads
    # as the pressed and checked state rather than as row striping.
    scheme.sets["Colors:Button"] = {
        **common,
        "BackgroundNormal": button,
        "BackgroundAlternate": mix(button, accent.color, 0.30),
    }
    # The inactive header swaps the two backgrounds rather than dimming the
    # text, which is what Breeze does; the dimmer text lives in [WM].
    scheme.sets["Colors:Header"] = {
        **common, "BackgroundNormal": header, "BackgroundAlternate": window,
    }
    scheme.sets["Colors:Header][Inactive"] = {
        **common, "BackgroundNormal": window, "BackgroundAlternate": header,
    }

    selection_fg = _selection_foreground(palette, roles, accent.color)
    scheme.sets["Colors:Selection"] = {
        **common,
        **_selection_hues(common, accent.color),
        "BackgroundNormal": accent.color,
        "BackgroundAlternate": mix(accent.color, background, 0.50),
        "ForegroundNormal": selection_fg,
        "ForegroundActive": selection_fg,
    }

    scheme.sets["Colors:Complementary"] = _complementary(
        scheme, common, roles, palette, accent.color, window
    )

    scheme.wm = {
        "activeBackground": header,
        "activeBlend": foreground if scheme.dark else header,
        "activeForeground": foreground,
        "inactiveBackground": window,
        "inactiveBlend": roles["base04"] if scheme.dark else window,
        "inactiveForeground": roles["base04"],
    }

    scheme.provenance = [
        ("background", background, "base00, the terminal background"),
        ("foreground", foreground, "base05"),
        ("dim text", roles["base04"], roles.provenance.get("base04", "")),
        ("accent", accent.color, accent.source),
        ("hover", hover.color, hover.source),
        ("window", window, f"{_pct(mapping, 'window')} background -> foreground"),
        ("button", button, f"{_pct(mapping, 'button')} background -> foreground"),
        ("header", header, f"{_pct(mapping, 'header')} background -> foreground"),
        ("alternate", alternate,
         f"{_pct(mapping, 'alternate')} background -> foreground"),
        ("negative", roles["base08"], roles.provenance.get("base08", "")),
        ("neutral", roles["base0A"], roles.provenance.get("base0A", "")),
        ("positive", roles["base0B"], roles.provenance.get("base0B", "")),
        ("link", roles["base0D"], roles.provenance.get("base0D", "")),
        ("visited", roles["base0E"], roles.provenance.get("base0E", "")),
    ]

    scheme.warnings.extend(_validate(scheme, background))
    return scheme


_SURFACE_DEFAULTS = {"alternate": 0.045, "window": 0.09, "button": 0.13, "header": 0.13}


def _pct(mapping: Mapping, key: str) -> str:
    return f"{mapping.surface(key, _SURFACE_DEFAULTS[key]) * 100:.1f}%"


def _complementary(
    scheme: Scheme,
    common: dict,
    roles: Roles,
    palette: Palette,
    accent: Color,
    window: Color,
) -> dict[str, Color]:
    """The set Plasma uses for full-screen and lock-screen surfaces.

    Both Breeze schemes make it dark, so a dark source simply reuses its own
    window surface. A light source has to invert, and the honest place to get
    a dark surface from a light scheme is the scheme itself: ANSI 0 is the
    darkest colour it states, and for a scheme with a dark counterpart -- as
    solarized has -- it is very often that counterpart's background exactly.
    Only when ANSI 0 is not actually dark does this fall back to blending.

    The accent is re-derived here rather than inherited. It was fitted to the
    light surfaces, and on a dark one it would leave the focus ring invisible.
    """
    if scheme.dark:
        return {
            **common,
            "BackgroundNormal": window,
            "BackgroundAlternate": mix(window, accent, 0.30),
        }

    dark_slot = palette.ansi[0]
    if dark_slot is not None and is_dark(dark_slot):
        surface, source = _hold_in_band(dark_slot), "color0"
    else:
        surface, source = _hold_in_band(roles["base05"]), "the foreground"

    text = roles["base00"]
    local = _usable(accent, (surface,), "the accent")
    scheme.warnings.append(
        f"the complementary set -- full-screen viewers, the lock and logout "
        f"screens -- is conventionally dark, so it was inverted from this "
        f"light scheme using {source} as its surface"
    )
    return {
        **common,
        "BackgroundNormal": surface,
        "BackgroundAlternate": mix(surface, text, 0.09),
        "ForegroundNormal": text,
        "ForegroundInactive": mix(surface, text, 0.72),
        "ForegroundActive": local.color,
        "DecorationFocus": local.color,
    }


# -- the gates ------------------------------------------------------------


def _validate(scheme: Scheme, background: Color) -> list[str]:
    """What Plasma will render badly, said plainly rather than shipped.

    None of these are fatal. KDE enforces no contrast requirement at all: an
    unreadable scheme installs and applies exactly like a readable one, which
    is why saying so here is the only warning anybody gets.

    Calibrated against Breeze, which has to pass: a gate that fires on the
    scheme every KDE desktop ships with is noise, not a finding.

    Findings are reported once per gate rather than once per colour set. The
    sets share their foregrounds, so a low-contrast scheme fails the same way
    seven times over, and seven near-identical lines teach nobody anything.
    """
    failures: dict[str, list[tuple[str, float]]] = {}

    def gate(key: str, label: str, ratio: float, target: float) -> None:
        if ratio < target:
            failures.setdefault(key, []).append((label, ratio))

    for name in SETS:
        values = scheme.sets[name]
        surface = values["BackgroundNormal"]
        label = name.replace("Colors:", "").replace("][", " ")

        # Selection is its own case. Breeze puts white on its accent blue at
        # 2.4:1 and sets DecorationFocus equal to the background, so the full
        # gates would flag upstream. It is small, transient, and always
        # bracketed by a surface that did pass, so it is held to the bar WCAG
        # allows large and incidental text, and to nothing else.
        if name == "Colors:Selection":
            gate("selection", label,
                 contrast_ratio(values["ForegroundNormal"], surface),
                 SELECTION_CONTRAST)
            continue

        gate("text", label,
             contrast_ratio(values["ForegroundNormal"], surface), TEXT_CONTRAST)
        gate("dim", label,
             contrast_ratio(values["ForegroundInactive"], surface), DIM_CONTRAST)
        gate("focus", label,
             contrast_ratio(values["DecorationFocus"], surface), DIM_CONTRAST)
        # Disabled text is not written: Plasma fades ForegroundNormal toward
        # the background and darkens the result, so this is what it becomes.
        gate("disabled", label,
             contrast_ratio(mix(values["ForegroundNormal"], surface, DISABLED_FADE),
                            surface),
             DISABLED_CONTRAST)

        if name in {"Colors:View", "Colors:Window"}:
            delta = abs(luminance(values["BackgroundAlternate"]) - luminance(surface))
            if delta < 0.0015:
                failures.setdefault("striping", []).append((label, delta))

    found = [_finding(key, hits) for key, hits in _GATE_ORDER(failures)]

    if not in_band(background):
        side = "dark" if luminance(background) < 0.5 else "light"
        found.append(
            f"the background is too {side} for Plasma to shade: KColorScheme "
            f"derives every frame, bevel and separator from it, and collapses "
            f"them onto one another at this luminance. The chrome around it was "
            f"held clear of that, so only frames inside text views are affected"
        )
    return found


#: Gate -> (what it measures, the bar it has to clear). Ordered by how much a
#: failure actually costs the person looking at the desktop.
_GATES = {
    "text": ("normal text", TEXT_CONTRAST),
    "dim": ("secondary text -- placeholders, sublines, inactive titlebars",
            DIM_CONTRAST),
    "focus": ("focus rings", DIM_CONTRAST),
    "disabled": ("disabled text, once Plasma fades it", DISABLED_CONTRAST),
    "selection": ("selected text against the highlight", SELECTION_CONTRAST),
}


def _GATE_ORDER(failures: dict) -> list[tuple[str, list]]:
    order = [*_GATES, "striping"]
    return [(key, failures[key]) for key in order if key in failures]


def _finding(key: str, hits: list[tuple[str, float]]) -> str:
    """One line covering every set that failed the same way."""
    if key == "striping":
        where = ", ".join(label for label, _ in hits)
        return (
            f"row striping is invisible in {where}: BackgroundAlternate is "
            f"indistinguishable from BackgroundNormal"
        )

    what, target = _GATES[key]
    label, worst = min(hits, key=lambda hit: hit[1])
    # Rounded *down*, so a ratio that failed can never be printed as its own
    # target: 1.98:1 reported as "2.0:1, below the 2.0:1 target" reads as a bug.
    worst = math.floor(worst * 10) / 10
    where = (
        f"in {label}" if len(hits) == 1
        else f"across {len(hits)} colour sets, worst in {label}"
    )
    return f"{what}: {worst:.1f}:1 {where}, below the {target}:1 target"


def warnings(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> list[str]:
    """Problems worth reporting before the file is written."""
    return resolve(
        palette, terminal_exact=terminal_exact, contrast_target=contrast_target
    ).warnings


# -- rendering ------------------------------------------------------------


def _header(palette: Palette, scheme: Scheme) -> list[str]:
    origin = f" from {palette.source_format}" if palette.source_format else ""
    lines = [
        f"# {single_line(palette.name) or 'cscx'}",
        f"# generated by cscx{origin}",
        "#",
        f"# {'dark' if scheme.dark else 'light'} scheme. Surfaces interpolated in",
        "# OKLab and held clear of the luminance where Plasma stops shading.",
        "#",
    ]
    width = max(len(name) for name, _, _ in scheme.provenance)
    for name, color, source in scheme.provenance:
        lines.append(f"#   {name:<{width}}  {color.hex}  {source}")

    for warning in scheme.warnings:
        lines.append("#")
        lines.append(f"# NOTE: {single_line(warning, limit=400)}")
    return lines


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> str:
    """Render `palette` as a Plasma `.colors` file."""
    scheme = resolve(
        palette, terminal_exact=terminal_exact, contrast_target=contrast_target
    )
    name = slug(palette.name)

    lines = _header(palette, scheme)
    lines += ["", EFFECTS]

    for section in SETS:
        lines += ["", f"[{section}]"]
        values = scheme.sets[section]
        lines += [f"{key}={values[key].rgb_triple}" for key in KEYS]

    lines += [
        "",
        "[General]",
        # Plasma finds a scheme by its file stem, so this has to agree with it.
        f"ColorScheme={name}",
        f"Name={single_line(palette.name) or name}",
        "shadeSortColumn=true",
        "",
        "[KDE]",
        # Breeze's own values: how strongly frames and separators are drawn.
        "contrast=4",
        "frameContrast=0.2",
        "",
        "[WM]",
    ]
    lines += [f"{key}={scheme.wm[key].rgb_triple}" for key in sorted(scheme.wm)]

    return "\n".join(lines) + "\n"
