"""konsole .colorscheme — INI sections holding decimal `r,g,b` triples."""

from __future__ import annotations

import configparser
import re

from ..color import ColorParseError, parse_color
from ..palette import Palette
from ._util import decode

NAME = "konsole"
ALIASES = ("kterminal",)
EXTENSIONS = (".colorscheme",)
BINARY = False

_RE_COLOR_SECTION = re.compile(r"^Color(\d)(Intense|Faint)?$", re.IGNORECASE)


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    if filename and filename.lower().endswith(".colorscheme"):
        return 0.95
    sections = len(re.findall(r"(?m)^\[Color\d(Intense|Faint)?\]\s*$", text))
    if sections and re.search(r"(?m)^Color\s*=\s*\d{1,3},\d{1,3},\d{1,3}", text):
        return min(0.6 + sections * 0.02, 0.93)
    return 0.0


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # konsole keys are CamelCase
    parser.read_string(text)

    palette = Palette(name=name, source_format=NAME)

    for section in parser.sections():
        color = _section_color(parser, section)
        if color is None:
            continue

        if m := _RE_COLOR_SECTION.match(section):
            slot, variant = int(m.group(1)), (m.group(2) or "").lower()
            if variant == "intense":
                palette.set_ansi(slot + 8, color)
            elif variant == "faint":
                palette.dim[slot] = color
            else:
                palette.set_ansi(slot, color)
            continue

        match section.lower():
            case "foreground":
                palette.foreground = color
            case "background":
                palette.background = color
            case "foregroundintense":
                palette.bright_foreground = color
            case "foregroundfaint":
                palette.dim_foreground = color
            case "backgroundintense" | "backgroundfaint":
                palette.extras.setdefault("konsole", {})[section] = color.hex

    if parser.has_section("General"):
        general = dict(parser.items("General"))
        if description := general.get("Description"):
            palette.name = description
        for key in ("Opacity", "Blur", "Wallpaper", "ColorRandomization"):
            if value := general.get(key):
                palette.extras.setdefault("konsole", {})[key] = value

    return palette


def _section_color(parser: configparser.ConfigParser, section: str):
    for key in ("Color", "color"):
        if parser.has_option(section, key):
            try:
                return parse_color(parser.get(section, key))
            except ColorParseError:
                return None
    return None
