"""Write a terminal palette as GTK colour overrides.

Two targets, because GTK is two theming stories that happen to share a name.

`gtk3` writes `@define-color` declarations, the mechanism Adwaita has used for
a decade. The names here are not invented or copied from a blog post: they are
the ones `libgtk-3.so` actually declares, cross-checked against the Breeze GTK3
theme, which defines the same core set. Notably absent is any link colour --
GTK3's Adwaita has none, so none is written.

`gtk4` writes CSS variables in a `:root` block, which is how libadwaita 1.9
takes overrides. Its older `@define-color` spellings still parse, but the
documentation is explicit that they "are aliases of UI colors or otherwise
derived from them" and "don't pick up overridden colors" -- so writing them
would be writing something inert.

Both files are colour overrides on top of whatever theme is in use, not themes
in themselves. That is the whole reason this is a tractable target: a real GTK
theme is thousands of lines of widget CSS, while the colours are a short list.

What is deliberately not written, in either file:

libadwaita derives every *standalone* colour -- `--accent-color` and friends,
used for coloured text on a neutral background -- from the matching background
colour, by an Oklab transform that clamps lightness to 0.5 on light schemes and
0.85 on dark. Overriding the background alone is the documented way to set an
app-wide accent; writing the standalone colour too would fight it.

The shades, borders and outlines -- `--shade-color`, `--card-shade-color`,
`--headerbar-border-color`, `--scrollbar-outline-color`, GTK3's `borders` at
the same job -- are translucent blacks and whites in both toolkits, sized to
work over any background. A palette holds opaque colours, so writing one there
would replace a working overlay with a flat slab. GTK3's `borders` is the one
exception, because Adwaita declares it as a real colour rather than an alpha.
"""

from __future__ import annotations

from dataclasses import dataclass

from .._text import single_line
from ..color import Color, contrast_ratio, mix
from ..editors.roles import Roles, derive
from ..mapping import Mapping, load as load_mapping
from ..palette import Palette
from ._common import (
    DIM_CONTRAST,
    TEXT_CONTRAST,
    accent_foreground,
    contrasting,
    pick_accent,
    ramp,
)

__all__ = ["GTK3", "GTK4"]


@dataclass(slots=True)
class Resolved:
    """Every colour both writers draw from."""

    background: Color        # the content surface, base00 verbatim
    foreground: Color
    dim: Color               # secondary and unfocused text
    recessive: Color         # disabled text
    window: Color            # general chrome
    header: Color            # header bars and title bars
    raised: Color            # cards, popovers, buttons -- above the window
    border: Color
    accent: Color
    accent_fg: Color
    accent_source: str
    red: Color
    green: Color
    yellow: Color
    dark: bool
    warnings: list[str]

    def on(self, background: Color) -> Color:
        """A foreground the toolkit asks for but does not supply."""
        return contrasting(background, self.foreground, self.background)


def resolve(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
    mapping: Mapping | None = None,
) -> Resolved:
    mapping = mapping or load_mapping()
    roles = derive(
        palette,
        terminal_exact=terminal_exact,
        contrast_target=contrast_target,
        mapping=mapping,
    )

    background, foreground = roles["base00"], roles["base05"]
    surface = ramp(background, foreground, mapping)

    window, header, raised = surface("window"), surface("header"), surface("button")
    accent = pick_accent(palette, roles, mapping, (background, window, header, raised))

    accent_fg = accent_foreground(palette, roles, accent)

    resolved = Resolved(
        background=background,
        foreground=foreground,
        dim=roles["base04"],
        recessive=roles["base03"],
        window=window,
        header=header,
        raised=raised,
        # base02 is the editor ramp's selection shade: a lift off the
        # background that is visible without becoming a second foreground,
        # which is exactly what a separator wants.
        border=roles["base02"],
        accent=accent.color,
        accent_fg=accent_fg,
        accent_source=accent.source,
        red=roles["base08"],
        green=roles["base0B"],
        yellow=roles["base0A"],
        dark=roles.background_is_dark,
        warnings=list(roles.warnings),
    )
    resolved.warnings.extend(_validate(resolved))
    return resolved


def _validate(r: Resolved) -> list[str]:
    """What will read badly, reported once per problem rather than per key."""
    found: list[str] = []

    surfaces = (("the content view", r.background), ("window chrome", r.window),
                ("header bars", r.header), ("cards and popovers", r.raised))

    worst = min(surfaces, key=lambda s: contrast_ratio(r.foreground, s[1]))
    ratio = contrast_ratio(r.foreground, worst[1])
    if ratio < TEXT_CONTRAST:
        found.append(
            f"normal text: {ratio:.1f}:1 at worst, on {worst[0]}, below the "
            f"{TEXT_CONTRAST}:1 target"
        )

    worst = min(surfaces, key=lambda s: contrast_ratio(r.dim, s[1]))
    ratio = contrast_ratio(r.dim, worst[1])
    if ratio < DIM_CONTRAST:
        found.append(
            f"secondary and unfocused text: {ratio:.1f}:1 at worst, on "
            f"{worst[0]}, below the {DIM_CONTRAST}:1 target"
        )

    for label, color in (("selected text", r.accent), ("error text", r.red),
                         ("success text", r.green), ("warning text", r.yellow)):
        fg = r.accent_fg if color is r.accent else r.on(color)
        ratio = contrast_ratio(fg, color)
        if ratio < DIM_CONTRAST:
            found.append(
                f"{label} on its own background: {ratio:.1f}:1, below the "
                f"{DIM_CONTRAST}:1 target"
            )
    return found


def warnings(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> list[str]:
    return resolve(
        palette, terminal_exact=terminal_exact, contrast_target=contrast_target
    ).warnings


# -- GTK 3 ----------------------------------------------------------------

#: `@define-color` names declared by libgtk-3.so, restricted to the ones a
#: palette can meaningfully set. Adwaita declares no link colour, so none is
#: written rather than one being invented.
def _gtk3_colors(r: Resolved) -> list[tuple[str, Color]]:
    unfocused_selection = mix(r.accent, r.window, 0.50)
    return [
        ("theme_bg_color", r.window),
        ("theme_fg_color", r.foreground),
        ("theme_base_color", r.background),
        ("theme_text_color", r.foreground),
        ("theme_selected_bg_color", r.accent),
        ("theme_selected_fg_color", r.accent_fg),
        ("theme_unfocused_bg_color", r.window),
        ("theme_unfocused_fg_color", r.dim),
        ("theme_unfocused_base_color", r.background),
        ("theme_unfocused_text_color", r.dim),
        ("theme_unfocused_selected_bg_color", unfocused_selection),
        ("theme_unfocused_selected_fg_color", r.on(unfocused_selection)),
        ("insensitive_bg_color", r.window),
        ("insensitive_fg_color", r.recessive),
        ("insensitive_base_color", r.background),
        ("borders", r.border),
        ("unfocused_borders", r.border),
        ("unfocused_insensitive_color", r.window),
        ("warning_color", r.yellow),
        ("error_color", r.red),
        ("success_color", r.green),
        ("content_view_bg", r.background),
        ("text_view_bg", r.background),
    ]


# -- GTK 4 / libadwaita ---------------------------------------------------

#: CSS variables libadwaita 1.9 takes overrides for, restricted to the
#: background/foreground pairs. Everything omitted is either derived by
#: libadwaita itself or a translucent overlay -- see the module docstring.
def _gtk4_colors(r: Resolved) -> list[tuple[str, Color]]:
    return [
        ("window-bg-color", r.window),
        ("window-fg-color", r.foreground),
        ("view-bg-color", r.background),
        ("view-fg-color", r.foreground),
        ("headerbar-bg-color", r.header),
        ("headerbar-fg-color", r.foreground),
        ("headerbar-backdrop-color", r.window),
        ("sidebar-bg-color", r.window),
        ("sidebar-fg-color", r.foreground),
        ("sidebar-backdrop-color", r.window),
        ("secondary-sidebar-bg-color", r.window),
        ("secondary-sidebar-fg-color", r.foreground),
        ("secondary-sidebar-backdrop-color", r.window),
        ("card-bg-color", r.raised),
        ("card-fg-color", r.foreground),
        ("dialog-bg-color", r.window),
        ("dialog-fg-color", r.foreground),
        ("popover-bg-color", r.raised),
        ("popover-fg-color", r.foreground),
        ("overview-bg-color", r.background),
        ("overview-fg-color", r.foreground),
        ("active-toggle-bg-color", r.raised),
        ("active-toggle-fg-color", r.foreground),
        ("thumbnail-bg-color", r.background),
        ("thumbnail-fg-color", r.foreground),
        ("accent-bg-color", r.accent),
        ("accent-fg-color", r.accent_fg),
        ("destructive-bg-color", r.red),
        ("destructive-fg-color", r.on(r.red)),
        ("success-bg-color", r.green),
        ("success-fg-color", r.on(r.green)),
        ("warning-bg-color", r.yellow),
        ("warning-fg-color", r.on(r.yellow)),
        ("error-bg-color", r.red),
        ("error-fg-color", r.on(r.red)),
    ]


# -- rendering ------------------------------------------------------------


def _header_lines(palette: Palette, r: Resolved, what: str) -> list[str]:
    origin = f" from {palette.source_format}" if palette.source_format else ""
    lines = [
        f"/* {single_line(palette.name) or 'cscx'}",
        f" * generated by cscx{origin}",
        " *",
        f" * {what}",
        f" * {'dark' if r.dark else 'light'} scheme; surfaces interpolated in OKLab.",
        f" * accent: {r.accent.hex} -- {r.accent_source}",
    ]
    for warning in r.warnings:
        lines.append(f" * NOTE: {single_line(warning, limit=300)}")
    lines.append(" */")
    return lines


class _Gtk:
    """One of the two GTK surfaces, differing only in how it spells a colour."""

    BINARY = False
    EXTENSION = ".css"

    def __init__(self, name: str, install: str, what: str) -> None:
        self.NAME = name
        self.FILENAME = "{name}." + name + ".css"
        self.INSTALL_PATH = install
        self._what = what

    def warnings(self, palette, *, terminal_exact=False, contrast_target=None):
        return warnings(
            palette, terminal_exact=terminal_exact, contrast_target=contrast_target
        )

    def emit(self, palette, *, terminal_exact=False, contrast_target=None) -> str:
        r = resolve(
            palette, terminal_exact=terminal_exact, contrast_target=contrast_target
        )
        lines = _header_lines(palette, r, self._what)
        lines.append("")

        if self.NAME == "gtk3":
            width = max(len(name) for name, _ in _gtk3_colors(r))
            lines += [
                f"@define-color {name:<{width}} {color.hex};"
                for name, color in _gtk3_colors(r)
            ]
        else:
            colors = _gtk4_colors(r)
            width = max(len(name) for name, _ in colors)
            lines.append(":root {")
            lines += [f"  --{name + ':':<{width + 1}} {color.hex};"
                      for name, color in colors]
            lines.append("}")

        return "\n".join(lines) + "\n"


GTK3 = _Gtk(
    "gtk3",
    "~/.config/gtk-3.0/gtk.css",
    "GTK 3 colour overrides, on top of whichever theme is in use.",
)

GTK4 = _Gtk(
    "gtk4",
    "~/.config/gtk-4.0/gtk.css",
    "GTK 4 / libadwaita colour overrides, on top of whichever theme is in use.",
)
