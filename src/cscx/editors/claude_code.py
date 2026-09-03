"""Claude Code theme output (`~/.claude/themes/<slug>.json`).

Claude Code is themable, and not by guesswork: it ships six presets, two of
which -- `dark-ansi` and `light-ansi` -- already render the whole interface
from the terminal's sixteen ANSI colors. If you want Claude Code to match the
terminal it runs in, set one of those and nothing needs generating.

This writer is for the other case: dressing Claude Code in a scheme that is
*not* the terminal's current one. It emits a custom theme, which Claude Code
reads as::

    {"name": ..., "base": <preset>, "overrides": {<token>: <colour>, ...}}

Two details make this worth doing carefully rather than approximately. Claude
Code drops any override whose token it does not recognise, and any value that
is not a valid colour -- silently, with no error -- so a guessed token name
would produce a theme that loads and does nothing. And the token-to-ANSI
mapping below is Anthropic's own, read out of the `dark-ansi` and `light-ansi`
presets in the installed binary rather than invented here; the two differ on
37 of the 72 tokens, so which base a scheme uses genuinely matters.
"""

from __future__ import annotations

import json

from .._text import single_line
from ..color import is_dark
from ..palette import ANSI_NAMES, Palette
from ._common import slug
from .roles import CONTRAST_TARGET

NAME = "claude-code"
EXTENSION = ".json"
FILENAME = "{name}.json"
BINARY = False
INSTALL_PATH = "~/.claude/themes/{name}.json"

#: Claude Code refers to a custom theme by this prefix in settings.json.
CUSTOM_PREFIX = "custom:"

#: Anthropic's own token mapping, read out of the `dark-ansi` preset in the
#: installed Claude Code. `ansi:<name>` resolves to a palette slot; anything
#: else is a literal Claude Code accepts as-is.
_DARK_ANSI = {
    "autoAccept": "ansi:magentaBright",
    "autoAcceptShimmer": "ansi:magentaBright",
    "skill": "ansi:magentaBright",
    "bashBorder": "ansi:magentaBright",
    "claude": "ansi:redBright",
    "claudeShimmer": "ansi:yellowBright",
    "claudeBlue_FOR_SYSTEM_SPINNER": "ansi:blueBright",
    "claudeBlueShimmer_FOR_SYSTEM_SPINNER": "ansi:blueBright",
    "permission": "ansi:blueBright",
    "permissionShimmer": "ansi:blueBright",
    "planMode": "ansi:cyanBright",
    "ide": "ansi:blue",
    "promptBorder": "ansi:white",
    "promptBorderShimmer": "ansi:whiteBright",
    "text": "ansi:whiteBright",
    "inverseText": "ansi:black",
    "inactive": "ansi:white",
    "inactiveShimmer": "ansi:whiteBright",
    "subtle": "ansi:white",
    "suggestion": "ansi:blueBright",
    "remember": "ansi:blueBright",
    "background": "ansi:cyanBright",
    "success": "ansi:greenBright",
    "error": "ansi:redBright",
    "warning": "ansi:yellowBright",
    "merged": "ansi:magentaBright",
    "warningShimmer": "ansi:yellowBright",
    "diffAdded": "ansi:green",
    "diffRemoved": "ansi:red",
    "diffAddedDimmed": "ansi:green",
    "diffRemovedDimmed": "ansi:red",
    "diffAddedWord": "ansi:greenBright",
    "diffRemovedWord": "ansi:redBright",
    "red_FOR_SUBAGENTS_ONLY": "ansi:redBright",
    "blue_FOR_SUBAGENTS_ONLY": "ansi:blueBright",
    "green_FOR_SUBAGENTS_ONLY": "ansi:greenBright",
    "yellow_FOR_SUBAGENTS_ONLY": "ansi:yellowBright",
    "purple_FOR_SUBAGENTS_ONLY": "ansi:magentaBright",
    "orange_FOR_SUBAGENTS_ONLY": "ansi:redBright",
    "pink_FOR_SUBAGENTS_ONLY": "ansi:magentaBright",
    "cyan_FOR_SUBAGENTS_ONLY": "ansi:cyanBright",
    "professionalBlue": "rgb(106,155,204)",
    "chromeYellow": "ansi:yellowBright",
    "clawd_body": "ansi:redBright",
    "clawd_background": "ansi:black",
    "userMessageBackground": "ansi:blackBright",
    "userMessageBackgroundHover": "ansi:white",
    "composerSidebarBackground": "ansi:blackBright",
    "selectionBg": "ansi:blue",
    "bashMessageBackgroundColor": "ansi:black",
    "memoryBackgroundColor": "ansi:blackBright",
    "rate_limit_fill": "ansi:yellow",
    "rate_limit_empty": "ansi:white",
    "fastMode": "ansi:redBright",
    "fastModeShimmer": "ansi:redBright",
    "effortUltra": "ansi:magentaBright",
    "briefLabelYou": "ansi:blueBright",
    "briefLabelClaude": "ansi:redBright",
    "rainbow_red": "ansi:red",
    "rainbow_orange": "ansi:redBright",
    "rainbow_yellow": "ansi:yellow",
    "rainbow_green": "ansi:green",
    "rainbow_blue": "ansi:cyan",
    "rainbow_indigo": "ansi:blue",
    "rainbow_violet": "ansi:magenta",
    "rainbow_red_shimmer": "ansi:redBright",
    "rainbow_orange_shimmer": "ansi:yellow",
    "rainbow_yellow_shimmer": "ansi:yellowBright",
    "rainbow_green_shimmer": "ansi:greenBright",
    "rainbow_blue_shimmer": "ansi:cyanBright",
    "rainbow_indigo_shimmer": "ansi:blueBright",
    "rainbow_violet_shimmer": "ansi:magentaBright",
}

#: The same for `light-ansi`. It differs on 37 of the 72 tokens, which is
#: why the base is chosen by the palette's lightness rather than fixed.
_LIGHT_ANSI = {
    "autoAccept": "ansi:magenta",
    "autoAcceptShimmer": "ansi:magentaBright",
    "skill": "ansi:magenta",
    "bashBorder": "ansi:magenta",
    "claude": "ansi:redBright",
    "claudeShimmer": "ansi:yellowBright",
    "claudeBlue_FOR_SYSTEM_SPINNER": "ansi:blue",
    "claudeBlueShimmer_FOR_SYSTEM_SPINNER": "ansi:blueBright",
    "permission": "ansi:blue",
    "permissionShimmer": "ansi:blueBright",
    "planMode": "ansi:cyan",
    "ide": "ansi:blueBright",
    "promptBorder": "ansi:white",
    "promptBorderShimmer": "ansi:whiteBright",
    "text": "ansi:black",
    "inverseText": "ansi:white",
    "inactive": "ansi:blackBright",
    "inactiveShimmer": "ansi:white",
    "subtle": "ansi:blackBright",
    "suggestion": "ansi:blue",
    "remember": "ansi:blue",
    "background": "ansi:cyan",
    "success": "ansi:green",
    "error": "ansi:red",
    "warning": "ansi:yellow",
    "merged": "ansi:magenta",
    "warningShimmer": "ansi:yellowBright",
    "diffAdded": "ansi:green",
    "diffRemoved": "ansi:red",
    "diffAddedDimmed": "ansi:green",
    "diffRemovedDimmed": "ansi:red",
    "diffAddedWord": "ansi:greenBright",
    "diffRemovedWord": "ansi:redBright",
    "red_FOR_SUBAGENTS_ONLY": "ansi:red",
    "blue_FOR_SUBAGENTS_ONLY": "ansi:blue",
    "green_FOR_SUBAGENTS_ONLY": "ansi:green",
    "yellow_FOR_SUBAGENTS_ONLY": "ansi:yellow",
    "purple_FOR_SUBAGENTS_ONLY": "ansi:magenta",
    "orange_FOR_SUBAGENTS_ONLY": "ansi:redBright",
    "pink_FOR_SUBAGENTS_ONLY": "ansi:magentaBright",
    "cyan_FOR_SUBAGENTS_ONLY": "ansi:cyan",
    "professionalBlue": "ansi:blueBright",
    "chromeYellow": "ansi:yellow",
    "clawd_body": "ansi:redBright",
    "clawd_background": "ansi:black",
    "userMessageBackground": "ansi:white",
    "userMessageBackgroundHover": "ansi:whiteBright",
    "composerSidebarBackground": "ansi:white",
    "selectionBg": "ansi:cyan",
    "bashMessageBackgroundColor": "ansi:whiteBright",
    "memoryBackgroundColor": "ansi:white",
    "rate_limit_fill": "ansi:yellow",
    "rate_limit_empty": "ansi:black",
    "fastMode": "ansi:red",
    "fastModeShimmer": "ansi:redBright",
    "effortUltra": "ansi:magenta",
    "briefLabelYou": "ansi:blue",
    "briefLabelClaude": "ansi:redBright",
    "rainbow_red": "ansi:red",
    "rainbow_orange": "ansi:redBright",
    "rainbow_yellow": "ansi:yellow",
    "rainbow_green": "ansi:green",
    "rainbow_blue": "ansi:cyan",
    "rainbow_indigo": "ansi:blue",
    "rainbow_violet": "ansi:magenta",
    "rainbow_red_shimmer": "ansi:redBright",
    "rainbow_orange_shimmer": "ansi:yellow",
    "rainbow_yellow_shimmer": "ansi:yellowBright",
    "rainbow_green_shimmer": "ansi:greenBright",
    "rainbow_blue_shimmer": "ansi:cyanBright",
    "rainbow_indigo_shimmer": "ansi:blueBright",
    "rainbow_violet_shimmer": "ansi:magentaBright",
}


#: The sixteen ANSI names Claude Code accepts, in slot order.
_SLOTS = {
    **{name: index for index, name in enumerate(ANSI_NAMES)},
    **{f"{name}Bright": index + 8 for index, name in enumerate(ANSI_NAMES)},
}

#: Tokens where the palette holds something better than an ANSI slot. Claude
#: Code's own ANSI presets cannot use these -- they only have sixteen colors to
#: work with -- but a real scheme carries them, so using them is more faithful
#: to the scheme rather than less.
_FROM_PALETTE = {
    "text": "foreground",
    "inverseText": "background",
    "selectionBg": "selection_background",
}


def emit(
    palette: Palette,
    *,
    terminal_exact: bool = False,
    contrast_target: float = CONTRAST_TARGET,
) -> str:
    """Render `palette` as a Claude Code custom theme.

    `terminal_exact` forces the ANSI mapping even where the palette holds a
    more specific colour; `contrast_target` is unused, since every value here
    comes from the scheme rather than being derived.
    """
    dark = palette.background is None or is_dark(palette.background)
    base = "dark-ansi" if dark else "light-ansi"
    mapping = _DARK_ANSI if dark else _LIGHT_ANSI

    overrides: dict[str, str] = {}
    for token, value in mapping.items():
        if not value.startswith("ansi:"):
            # A handful of tokens are literal even in the ANSI presets; there
            # is no palette slot to substitute, so Anthropic's value stands.
            overrides[token] = value
            continue

        color = None
        if not terminal_exact and (field := _FROM_PALETTE.get(token)):
            color = getattr(palette, field, None)
        if color is None:
            color = palette.ansi[_SLOTS[value.removeprefix("ansi:")]]
        if color is not None:
            overrides[token] = color.hex

    theme = {
        "name": single_line(palette.name) or slug(palette.name),
        "base": base,
        "overrides": overrides,
    }
    return json.dumps(theme, indent=2) + "\n"
