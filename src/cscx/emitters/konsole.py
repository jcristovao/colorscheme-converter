"""konsole .colorscheme output — INI sections of decimal `r,g,b` triples."""

from __future__ import annotations

from .._text import single_line
from ..color import Color, ColorParseError, parse_color
from ..fill import Derivations
from ..palette import Palette
from ._util import GENERATED_BY

NAME = "konsole"
EXTENSION = ".colorscheme"
BINARY = False


def emit(palette: Palette, derived: Derivations | None = None) -> str:
    lines: list[str] = []
    extras = palette.extras.get("konsole") or {}

    for slot in range(8):
        _entry(lines, f"Color{slot}", palette.ansi[slot])
        _entry(lines, f"Color{slot}Intense", palette.ansi[slot + 8])
        _entry(lines, f"Color{slot}Faint", palette.dim[slot])

    _entry(lines, "Background", palette.background)
    _entry(lines, "BackgroundIntense", _extra(extras, "BackgroundIntense"))
    _entry(lines, "BackgroundFaint", _extra(extras, "BackgroundFaint"))
    _entry(lines, "Foreground", palette.foreground)
    _entry(lines, "ForegroundIntense", palette.bright_foreground)
    _entry(lines, "ForegroundFaint", palette.dim_foreground)

    # konsole's parser wants a [General] block; Description is where the
    # scheme name lives, and doubles as the provenance line.
    lines.append("[General]")
    lines.append(f"Description={single_line(palette.name) or 'cscx'}")
    for key in ("Opacity", "Blur", "Wallpaper", "ColorRandomization"):
        if key in extras:
            lines.append(f"{key}={extras[key]}")
    lines.append(f"# {GENERATED_BY} from {palette.source_format or 'unknown'}")

    return "\n".join(lines) + "\n"


def _entry(lines: list[str], section: str, color: Color | None) -> None:
    if color is None:
        return
    lines.append(f"[{section}]")
    lines.append(f"Color={color.rgb_triple}")
    lines.append("")


def _extra(extras: dict, key: str) -> Color | None:
    """konsole's own intense/faint backgrounds, kept from a konsole source."""
    if key not in extras:
        return None
    try:
        return parse_color(extras[key])
    except ColorParseError:
        return None
