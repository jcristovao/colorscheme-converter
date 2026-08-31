"""kitty.conf — whitespace-separated `key value` pairs."""

from __future__ import annotations

import re

from ..color import ColorParseError, parse_color
from ..palette import Palette
from ._util import config_lines, decode, split_kv

NAME = "kitty"
ALIASES = ("kitty.conf",)
EXTENSIONS = (".conf",)
BINARY = False

_RE_COLOR_N = re.compile(r"^color(\d{1,3})$")

# Direct key -> palette attribute.
_SCALARS = {
    "background": "background",
    "foreground": "foreground",
    "cursor": "cursor",
    "cursor_text_color": "cursor_text",
    "selection_background": "selection_background",
    "selection_foreground": "selection_foreground",
}

# Colors kitty defines that have no slot in the canonical model. Keeping them
# means a kitty -> kitty round trip does not silently lose the tab bar.
_EXTRA_KEYS = frozenset({
    "url_color", "active_border_color", "inactive_border_color",
    "bell_border_color", "visual_bell_color", "active_tab_foreground",
    "active_tab_background", "inactive_tab_foreground",
    "inactive_tab_background", "tab_bar_background", "tab_bar_margin_color",
    "mark1_foreground", "mark1_background", "mark2_foreground",
    "mark2_background", "mark3_foreground", "mark3_background",
    "macos_titlebar_color", "wayland_titlebar_color",
})

# kitty lets one color refer to another by name instead of a literal value.
_REFERENCES = {"background", "foreground", "none"}


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    if filename and filename.lower() == "kitty.conf":
        return 0.95

    # The giveaway is `colorN <value>` with no `=` between them.
    hits = len(re.findall(r"(?m)^\s*color\d{1,3}\s+[#a-zA-Z0-9]", text))
    if not hits:
        # A kitty theme file can omit colorN and still set fg/bg.
        if re.search(r"(?m)^\s*(background|foreground)\s+#[0-9a-fA-F]{3,6}\s*$", text):
            return 0.5
        return 0.0

    score = 0.55 + min(hits, 16) * 0.025
    if re.search(r"(?m)^\s*(font_family|bold_is_bright|shell_integration|scrollback_lines)\s", text):
        score += 0.1
    return min(score, 0.95)


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    palette = Palette(name=name, source_format=NAME)
    deferred: dict[str, str] = {}

    for _lineno, line in config_lines(text):
        pair = split_kv(line, separators="")  # kitty separates on whitespace
        if pair is None:
            continue
        key, value = pair
        key = key.lower()
        # kitty ignores anything after the first token of a color value.
        value = value.split()[0] if value.split() else value

        if m := _RE_COLOR_N.match(key):
            index = int(m.group(1))
            if index <= 255:
                palette.set_indexed(index, _safe_color(value))
            continue

        if key in _SCALARS:
            if value.lower() in _REFERENCES:
                deferred[key] = value.lower()
            else:
                setattr(palette, _SCALARS[key], _safe_color(value))
            continue

        if key in _EXTRA_KEYS:
            if (color := _safe_color(value)) is not None:
                palette.extras.setdefault("kitty", {})[key] = color.hex

    _resolve_references(palette, deferred)
    return palette


def _safe_color(value: str):
    """Parse a value, returning `None` rather than raising on junk.

    A theme file is not a program: one unreadable line should not cost the
    user the other fifteen colors.
    """
    try:
        return parse_color(value)
    except ColorParseError:
        return None


def _resolve_references(palette: Palette, deferred: dict[str, str]) -> None:
    """Apply `cursor_text_color background` style indirections, post-parse."""
    for key, target in deferred.items():
        if target == "none":
            continue
        resolved = palette.background if target == "background" else palette.foreground
        if resolved is not None:
            setattr(palette, _SCALARS[key], resolved)
