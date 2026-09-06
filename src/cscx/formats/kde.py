"""KDE Plasma .colors — read-only, and deliberately narrow.

This parser exists for two reasons, neither of which is "convert KDE schemes
into good terminal schemes".

The first is that it is the round-trip oracle for the KDE writer. Everything
else in this package is checked by emitting a palette, reading it back and
asserting that nothing was lost and nothing was invented; without a reader the
KDE writer could not take part in that.

The second is discovery: `cscx browse` and `cscx detect` can see the schemes
already installed on the machine.

What it does *not* do is pretend the reverse conversion is worth much. A
`.colors` file holds no bright variants, no dim, no cursor, and only six
hues -- and in practice not even six, because every scheme in the wild copies
Breeze's semantic constants verbatim. `ForegroundNegative=218,68,83`,
`ForegroundNeutral=246,116,0`, `ForegroundPositive=39,174,96` and
`ForegroundVisited=155,89,182` are byte-identical in Breeze Light and Breeze
Dark, so converting either one produces the same six hues.

Only the values the writer puts down verbatim from the palette are read back.
`ForegroundActive` and `DecorationFocus` hold the accent, which may be the
scheme's selection colour rather than any ANSI slot, so reading them would
invent a `color6` the source never had. Same for `Colors:Selection`. Ten of
the sixteen slots come back `None`, which is the honest answer.
"""

from __future__ import annotations

import configparser
import re

from ..color import ColorParseError, parse_color
from ..palette import Palette
from ._util import decode

NAME = "kde"
ALIASES = ("plasma", "kde-plasma")
EXTENSIONS = (".colors",)
BINARY = False

#: KDE key -> ANSI slot. Exactly the values `desktops/kde.py` writes straight
#: out of the palette, which is what makes the round trip mean anything.
_SLOTS = {
    "ForegroundNegative": 1,   # base08, red
    "ForegroundPositive": 2,   # base0B, green
    "ForegroundNeutral": 3,    # base0A, yellow
    "ForegroundLink": 4,       # base0D, blue
    "ForegroundVisited": 5,    # base0E, magenta
    "DecorationHover": 6,      # base0C, cyan
}

#: The content set: a `.colors` file's closest thing to a terminal.
_VIEW = "Colors:View"

_RE_SET = re.compile(r"(?m)^\[Colors:(View|Window|Button|Selection|Tooltip)\]")
_RE_BACKGROUND = re.compile(r"(?m)^BackgroundNormal\s*=")

#: `/etc/xdg/colors/*.colors` are GIMP palette files for KDE's colour picker --
#: an unrelated format that happens to share the extension. Sniffing on the
#: extension alone would claim them.
_GIMP = "GIMP Palette"


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    if text.lstrip().startswith(_GIMP):
        return 0.0

    sets = len(_RE_SET.findall(text))
    if sets and _RE_BACKGROUND.search(text):
        return min(0.90 + sets * 0.01, 0.97)
    if filename and filename.lower().endswith(".colors") and sets:
        return 0.80
    return 0.0


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # KDE keys are CamelCase
    parser.read_string(text)

    palette = Palette(name=name, source_format=NAME)

    if parser.has_section(_VIEW):
        view = parser[_VIEW]
        palette.background = _safe_color(view.get("BackgroundNormal"))
        palette.foreground = _safe_color(view.get("ForegroundNormal"))
        for key, slot in _SLOTS.items():
            palette.set_ansi(slot, _safe_color(view.get(key)))

    if parser.has_section("General"):
        general = parser["General"]
        if display := general.get("Name"):
            palette.name = display

    return palette


def _safe_color(raw: str | None):
    """One unreadable value costs that value, not the rest of the file."""
    if raw is None:
        return None
    try:
        return parse_color(raw)
    except ColorParseError:
        return None
