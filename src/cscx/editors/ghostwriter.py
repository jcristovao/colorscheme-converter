"""ghostwriter theme output (`~/.local/share/ghostwriter/themes/<Name>.json`).

ghostwriter is a distraction-free Markdown editor, so it has no syntax groups
in the usual sense. It has eleven colours, and its own reader derives seven
more from them::

    headingMarkup = inlineHtml = codeMarkup = blockquoteMarkup
                  = divider    = markup
    codeText      = block
    image         = link

So the writer's whole job is picking eleven values, and the interesting part
is that this project has already decided most of them. `groups.py` carries
cscx's Markdown conventions for every other editor -- `@markup.heading` is
base0D, `@markup.list` base08, `@markup.quote` base0C, `@markup.link.url`
base09 -- and reusing them means a ghostwriter theme and a neovim theme
generated from one palette agree about what a heading looks like.

Two structural details, both taken from ghostwriter's own `ThemeRepository`
rather than guessed.

The theme's *name is its filename*: nothing inside the document records it,
and `availableThemes()` is built from the directory listing. And every one of
the eleven keys must be present and parse as a colour, because the loader ands
its results together and reports "Invalid or missing value(s)" for the whole
file if any single one fails.
"""

from __future__ import annotations

import json

from ..palette import Palette
from ._common import slug
from .roles import derive

NAME = "ghostwriter"
EXTENSION = ".json"
#: Qualified, unlike the install path, because `--to all` writes every target
#: into one directory and Claude Code also wants `{name}.json` there. Where it
#: actually matters -- the themes directory -- INSTALL_PATH keeps the bare name
#: ghostwriter requires, and that is what `activate` and the browser's copy use.
FILENAME = "{name}.ghostwriter.json"
BINARY = False
#: The name is carried by the filename alone: the document has no name field,
#: and ThemeRepository builds its theme list from this directory's contents.
INSTALL_PATH = "~/.local/share/ghostwriter/themes/{name}.json"

#: ghostwriter key -> role, as a fallback chain. Every entry is a decision
#: `groups.py` already made for the other editors, so one palette dresses them
#: all the same way:
#:
#:   heading   @markup.heading     base0D
#:   accent    @markup.list        base08   (bound to listMarkup)
#:   block     @markup.quote       base0C   (code text inherits it)
#:   link      @markup.link.url    base09   (images inherit it)
#:   error     @comment.error      base08
#:
#: `markup` is every syntax character at once -- the hashes, asterisks, angle
#: brackets, backticks and rules -- which wants the recessive-but-readable
#: role. base03 is exactly that, and it is the one shade whose contrast
#: against the background is guaranteed rather than hoped for.
#:
#: `emphasis` has no counterpart: cscx renders bold and italic as attributes
#: and gives them no colour of their own, while ghostwriter must have one.
#: base0E is the base16 convention for it, and is not otherwise claimed here.
COLORS = {
    "background": "base00",
    "foreground": "base05",
    "selection": "selection_bg|base02",
    "cursor": "cursor|base0D",
    "markup": "base03",
    "accent": "base08",
    "heading": "base0D",
    "emphasis": "base0E",
    "block": "base0C",
    "link": "base09",
    "error": "base08",
}


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float | None = None,
) -> str:
    """Render `palette` as a ghostwriter theme document.

    Written as a single colour scheme rather than the `{"light": ..., "dark":
    ...}` pair ghostwriter also accepts. A palette has one polarity, and
    claiming a dark scheme that was never supplied would mean inventing one.
    ghostwriter handles the single-scheme form by ignoring its own dark mode
    toggle, which its tooltip already tells the user to expect: "If the current
    theme does not support a dark color scheme, then this option will have no
    effect."
    """
    roles = derive(
        palette, terminal_exact=terminal_exact, contrast_target=contrast_target
    )

    document = {key: roles.resolve(chain).hex for key, chain in COLORS.items()}
    return json.dumps(document, indent=2) + "\n"


def theme_name(palette: Palette) -> str:
    """What the theme will be called, which is to say what to name the file."""
    return slug(palette.name)
