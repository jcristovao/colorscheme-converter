"""Obsidian theme output (`<vault>/.obsidian/themes/<name>/theme.css`).

An Obsidian theme is a stylesheet, and nearly all of a good one is custom
properties. The application's own `app.css` is built in two layers: a dozen
*foundation* colours -- a neutral scale, eight named hues and an accent --
and several hundred *semantic* variables defined in terms of them::

    --background-primary:   var(--color-base-00)
    --background-secondary: var(--color-base-20)
    --text-muted:           var(--color-base-70)
    --text-faint:           var(--color-base-50)
    --code-comment:         var(--text-faint)
    --text-error:           var(--color-red)

So the writer sets the foundations and lets Obsidian derive the rest, which
is both less to get wrong and what its documentation asks themes to do. The
semantic layer is touched only where this project has already made a decision
Obsidian's defaults would contradict: `groups.py` says a heading is base0D and
a keyword base0E for every other editor, and reusing those means an Obsidian
theme and a neovim theme generated from one palette agree.

Three structural details, all read out of Obsidian rather than guessed.

Themes are *per vault*: there is no user-wide themes directory, so the install
path names a vault that only the caller can supply. A theme is a *directory*
holding this stylesheet and a `manifest.json`, and the directory's name must
equal the manifest's `name` exactly -- `manifest()` writes that half, and
`activate` places both. And the stylesheet declares its polarity by selector:
variables under `.theme-dark` apply only while the vault's base colour scheme
is dark. A palette has one polarity, so exactly one of the two is written.
"""

from __future__ import annotations

import colorsys
import json

from ..color import Color, contrast_ratio, mix
from ..palette import Palette
from ._common import header_lines, slug
from .roles import Roles, derive

NAME = "obsidian"
EXTENSION = ".css"
#: Qualified, because `--to all` writes every target into one directory.
#: Where it matters -- inside the vault -- the file must be called
#: `theme.css`, and INSTALL_PATH says so.
FILENAME = "{name}.obsidian.css"
BINARY = False
#: `<vault>` is not a template field: no default could be right, so
#: `activate` takes the vault explicitly and refuses to guess one.
INSTALL_PATH = "<vault>/.obsidian/themes/{name}/theme.css"

#: The oldest Obsidian whose stylesheet has the variables written here. 1.0
#: introduced `--color-base-*` and the named hues together.
MIN_APP_VERSION = "1.0.0"

#: Obsidian's neutral scale, from the background (00) to normal text (100),
#: as `(from, to, t)` between two base16 roles. Four of the twelve steps *are*
#: roles, chosen by what Obsidian uses the step for:
#:
#:   25   form fields           base01, the cursorline shade
#:   35   hovered borders       base02, the statusline shade
#:   50   --text-faint          base03, the one shade with guaranteed contrast
#:   70   --text-muted          base04
#:
#: base03 at 50 is the one that matters. Obsidian renders code comments, list
#: markers and Markdown syntax characters in `--text-faint`, and those are
#: exactly what base03 is held at 4.5:1 for. The steps in between are spaced
#: the way Obsidian's own default scale is.
SCALE = {
    "00": ("base00", "base00", 0.0),
    "05": ("base00", "base01", 0.25),
    "10": ("base00", "base01", 0.40),
    "20": ("base00", "base01", 0.65),
    "25": ("base01", "base01", 0.0),
    "30": ("base01", "base02", 0.25),
    "35": ("base02", "base02", 0.0),
    "40": ("base02", "base03", 0.40),
    "50": ("base03", "base03", 0.0),
    "60": ("base03", "base04", 0.50),
    "70": ("base04", "base04", 0.0),
    "100": ("base05", "base05", 0.0),
}

#: Obsidian's eight named hues. Seven are base16 accents outright. `pink` is
#: the one base16 has no word for; see `_pink`.
HUES = {
    "red": "base08",
    "orange": "base09",
    "yellow": "base0A",
    "green": "base0B",
    "cyan": "base0C",
    "blue": "base0D",
    "purple": "base0E",
}

#: The accent: links, tags, checkboxes, the active tab, focus rings. base0D is
#: what `groups.py` gives headings and directories, and what both Obsidian's
#: default accent and base16 mean by "the highlighted thing".
ACCENT = "base0D"

#: Semantic variables set directly, as fallback chains. Each is here because
#: Obsidian's default would disagree with a decision made elsewhere:
#:
#:   headings      @markup.heading     base0D
#:   list markers  @markup.list        base08
#:   blockquotes   @markup.quote       base0C
#:   links         @markup.link.url    base09
#:
#: and the same for code, where Obsidian's defaults (functions yellow,
#: keywords pink, operators red) are a different convention from base16's.
#: Bold and italic are absent on purpose: cscx renders them as attributes and
#: gives them no colour, and Obsidian's default for both is to inherit.
VARIABLES = {
    # The terminal's own selection and cursor, wherever the source had them.
    "text-selection": "selection_bg|base02",
    "caret-color": "cursor|base05",

    "h1-color": "base0D",
    "h2-color": "base0D",
    "h3-color": "base0D",
    "h4-color": "base0D",
    "h5-color": "base0D",
    "h6-color": "base0D",
    "list-marker-color": "base08",
    "blockquote-color": "base0C",
    "link-color": "base09",
    "link-external-color": "base09",
    "link-unresolved-color": "base09",

    "code-comment": "base03",
    "code-function": "base0D",
    "code-keyword": "base0E",
    "code-string": "base0B",
    "code-operator": "base05",
    "code-punctuation": "base05",
    "code-property": "base08",
    "code-tag": "base0A",
    "code-value": "base09",
    "code-important": "base0C",
}

#: How strongly `==highlighted==` text is tinted with base0A, the search
#: colour everywhere else. Obsidian's own default is a 40% yellow.
HIGHLIGHT_ALPHA = 0.4


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> str:
    """Render `palette` as an Obsidian `theme.css`."""
    roles = derive(
        palette, terminal_exact=terminal_exact, contrast_target=contrast_target
    )

    hues = {name: roles[role] for name, role in HUES.items()}
    hues["pink"] = _pink(palette, roles)
    accent = roles[ACCENT]

    declarations: list[tuple[str, str]] = []
    for step in SCALE:
        declarations.append((f"color-base-{step}", _step(roles, step).hex))
    for name, color in hues.items():
        declarations.append((f"color-{name}", color.hex))
    # Deprecated since Obsidian 1.13 in favour of color-mix(), but its own
    # stylesheet still carries them "for theme compatibility" and plugins
    # still read them. Left at their defaults they would tint callouts in
    # Obsidian's hues while everything else used this palette's.
    for name, color in hues.items():
        declarations.append((f"color-{name}-rgb", _triple(color)))

    hue, saturation, lightness = _hsl(accent)
    declarations += [
        ("accent-h", str(hue)),
        ("accent-s", f"{saturation}%"),
        ("accent-l", f"{lightness}%"),
        ("text-on-accent", _on(accent, roles).hex),
    ]

    for variable, chain in VARIABLES.items():
        color = roles.resolve(chain)
        assert color is not None  # every chain ends in a base16 role
        declarations.append((variable, color.hex))
    declarations.append((
        "text-highlight-bg",
        f"rgba({_triple(roles['base0A'])}, {HIGHLIGHT_ALPHA})",
    ))

    selector = ".theme-dark" if roles.background_is_dark else ".theme-light"
    name = slug(palette.name)
    lines = [
        _comment(line)
        for line in header_lines(palette, roles, "")
        + [
            "",
            f"install as {INSTALL_PATH.format(name=name)}, beside a",
            f'manifest.json naming it "{name}"; then pick it under',
            "Settings > Appearance > Themes.",
        ]
    ]
    lines += ["", f"{selector} {{"]
    lines += [f"  --{variable}: {value};" for variable, value in declarations]
    lines += ["}", ""]
    return "\n".join(lines)


def manifest(name: str) -> str:
    """The `manifest.json` that makes a directory a theme.

    `name` must be the directory's own name: Obsidian matches the two exactly
    and lists nothing for a directory whose manifest disagrees with it.
    """
    document = {
        "name": name,
        "version": "1.0.0",
        "minAppVersion": MIN_APP_VERSION,
        "author": "cscx",
    }
    return json.dumps(document, indent=2) + "\n"


def _step(roles: Roles, step: str) -> Color:
    """One step of the neutral scale.

    Under `--terminal-exact` nothing may be blended, so an in-between step
    takes whichever of its two roles it sits nearer. The scale gets flatter,
    which is the trade that flag always makes.
    """
    start, end, t = SCALE[step]
    if start == end:
        return roles[start]
    if roles.terminal_exact:
        return roles[end if t >= 0.5 else start]
    return mix(roles[start], roles[end], t)


def _pink(palette: Palette, roles: Roles) -> Color:
    """Obsidian's eighth hue, which neither a terminal nor base16 has.

    Handled the way `roles.py` handles orange: blended from the two hues that
    bracket it, or taken from the bright variant when blending is forbidden.
    """
    if roles.terminal_exact:
        return palette.ansi[13]
    return mix(roles["base08"], roles["base0E"], 0.5)


def _on(background: Color, roles: Roles) -> Color:
    """Text for an accent-coloured button: whichever end of the scale reads."""
    return max(
        (roles["base07"], roles["base00"]),
        key=lambda candidate: contrast_ratio(candidate, background),
    )


def _hsl(color: Color) -> tuple[int, int, int]:
    """Hue in degrees, saturation and lightness in percent.

    The accent is the one colour Obsidian wants in pieces, because it builds
    its hover and active shades by doing arithmetic on the lightness.
    """
    red, green, blue = (channel / 255 for channel in (color.r, color.g, color.b))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    return round(hue * 360) % 360, round(saturation * 100), round(lightness * 100)


def _triple(color: Color) -> str:
    return f"{color.r}, {color.g}, {color.b}"


def _comment(text: str) -> str:
    """One self-contained CSS comment.

    Each line opens and closes its own, so that no line depends on another
    for being a comment at all, and the one sequence that could end it early
    is taken apart. A scheme name is free text; `*/` in one would otherwise
    turn the rest of the header into stylesheet.
    """
    return f"/* {text.strip().replace('*/', '* /')} */".replace("/*  */", "/* */")


def theme_name(palette: Palette) -> str:
    """What the theme will be called: its directory, and its manifest's name."""
    return slug(palette.name)
