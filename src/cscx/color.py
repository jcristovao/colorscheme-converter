"""The canonical color value and the parsers for every spelling of one."""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Color", "ColorParseError", "parse_color"]


class ColorParseError(ValueError):
    """Raised when a string cannot be read as a color."""


# CSS Level 4 / X11 shared names. Terminal configs that accept names (ghostty,
# Xresources, Windows Terminal) draw from this set, so we carry it inline
# rather than depending on /usr/share/X11/rgb.txt, which is not always present.
_NAMED = {
    "aliceblue": 0xF0F8FF, "antiquewhite": 0xFAEBD7, "aqua": 0x00FFFF,
    "aquamarine": 0x7FFFD4, "azure": 0xF0FFFF, "beige": 0xF5F5DC,
    "bisque": 0xFFE4C4, "black": 0x000000, "blanchedalmond": 0xFFEBCD,
    "blue": 0x0000FF, "blueviolet": 0x8A2BE2, "brown": 0xA52A2A,
    "burlywood": 0xDEB887, "cadetblue": 0x5F9EA0, "chartreuse": 0x7FFF00,
    "chocolate": 0xD2691E, "coral": 0xFF7F50, "cornflowerblue": 0x6495ED,
    "cornsilk": 0xFFF8DC, "crimson": 0xDC143C, "cyan": 0x00FFFF,
    "darkblue": 0x00008B, "darkcyan": 0x008B8B, "darkgoldenrod": 0xB8860B,
    "darkgray": 0xA9A9A9, "darkgreen": 0x006400, "darkgrey": 0xA9A9A9,
    "darkkhaki": 0xBDB76B, "darkmagenta": 0x8B008B, "darkolivegreen": 0x556B2F,
    "darkorange": 0xFF8C00, "darkorchid": 0x9932CC, "darkred": 0x8B0000,
    "darksalmon": 0xE9967A, "darkseagreen": 0x8FBC8F, "darkslateblue": 0x483D8B,
    "darkslategray": 0x2F4F4F, "darkslategrey": 0x2F4F4F,
    "darkturquoise": 0x00CED1, "darkviolet": 0x9400D3, "deeppink": 0xFF1493,
    "deepskyblue": 0x00BFFF, "dimgray": 0x696969, "dimgrey": 0x696969,
    "dodgerblue": 0x1E90FF, "firebrick": 0xB22222, "floralwhite": 0xFFFAF0,
    "forestgreen": 0x228B22, "fuchsia": 0xFF00FF, "gainsboro": 0xDCDCDC,
    "ghostwhite": 0xF8F8FF, "gold": 0xFFD700, "goldenrod": 0xDAA520,
    "gray": 0x808080, "green": 0x008000, "greenyellow": 0xADFF2F,
    "grey": 0x808080, "honeydew": 0xF0FFF0, "hotpink": 0xFF69B4,
    "indianred": 0xCD5C5C, "indigo": 0x4B0082, "ivory": 0xFFFFF0,
    "khaki": 0xF0E68C, "lavender": 0xE6E6FA, "lavenderblush": 0xFFF0F5,
    "lawngreen": 0x7CFC00, "lemonchiffon": 0xFFFACD, "lightblue": 0xADD8E6,
    "lightcoral": 0xF08080, "lightcyan": 0xE0FFFF,
    "lightgoldenrodyellow": 0xFAFAD2, "lightgray": 0xD3D3D3,
    "lightgreen": 0x90EE90, "lightgrey": 0xD3D3D3, "lightpink": 0xFFB6C1,
    "lightsalmon": 0xFFA07A, "lightseagreen": 0x20B2AA,
    "lightskyblue": 0x87CEFA, "lightslategray": 0x778899,
    "lightslategrey": 0x778899, "lightsteelblue": 0xB0C4DE,
    "lightyellow": 0xFFFFE0, "lime": 0x00FF00, "limegreen": 0x32CD32,
    "linen": 0xFAF0E6, "magenta": 0xFF00FF, "maroon": 0x800000,
    "mediumaquamarine": 0x66CDAA, "mediumblue": 0x0000CD,
    "mediumorchid": 0xBA55D3, "mediumpurple": 0x9370DB,
    "mediumseagreen": 0x3CB371, "mediumslateblue": 0x7B68EE,
    "mediumspringgreen": 0x00FA9A, "mediumturquoise": 0x48D1CC,
    "mediumvioletred": 0xC71585, "midnightblue": 0x191970,
    "mintcream": 0xF5FFFA, "mistyrose": 0xFFE4E1, "moccasin": 0xFFE4B5,
    "navajowhite": 0xFFDEAD, "navy": 0x000080, "oldlace": 0xFDF5E6,
    "olive": 0x808000, "olivedrab": 0x6B8E23, "orange": 0xFFA500,
    "orangered": 0xFF4500, "orchid": 0xDA70D6, "palegoldenrod": 0xEEE8AA,
    "palegreen": 0x98FB98, "paleturquoise": 0xAFEEEE,
    "palevioletred": 0xDB7093, "papayawhip": 0xFFEFD5, "peachpuff": 0xFFDAB9,
    "peru": 0xCD853F, "pink": 0xFFC0CB, "plum": 0xDDA0DD, "powderblue": 0xB0E0E6,
    "purple": 0x800080, "rebeccapurple": 0x663399, "red": 0xFF0000,
    "rosybrown": 0xBC8F8F, "royalblue": 0x4169E1, "saddlebrown": 0x8B4513,
    "salmon": 0xFA8072, "sandybrown": 0xF4A460, "seagreen": 0x2E8B57,
    "seashell": 0xFFF5EE, "sienna": 0xA0522D, "silver": 0xC0C0C0,
    "skyblue": 0x87CEEB, "slateblue": 0x6A5ACD, "slategray": 0x708090,
    "slategrey": 0x708090, "snow": 0xFFFAFA, "springgreen": 0x00FF7F,
    "steelblue": 0x4682B4, "tan": 0xD2B48C, "teal": 0x008080,
    "thistle": 0xD8BFD8, "tomato": 0xFF6347, "turquoise": 0x40E0D0,
    "violet": 0xEE82EE, "wheat": 0xF5DEB3, "white": 0xFFFFFF,
    "whitesmoke": 0xF5F5F5, "yellow": 0xFFFF00, "yellowgreen": 0x9ACD32,
}


@dataclass(frozen=True, slots=True)
class Color:
    """An 8-bit-per-channel sRGB color, with optional alpha.

    Alpha is carried because a few formats (Windows Terminal, konsole opacity,
    ghostty background-opacity) can express it; emitters that cannot represent
    it drop it rather than failing.
    """

    r: int
    g: int
    b: int
    a: float | None = None

    def __post_init__(self) -> None:
        for name in ("r", "g", "b"):
            v = getattr(self, name)
            if not isinstance(v, int) or not 0 <= v <= 255:
                raise ColorParseError(f"channel {name}={v!r} outside 0-255")
        if self.a is not None and not 0.0 <= self.a <= 1.0:
            raise ColorParseError(f"alpha={self.a!r} outside 0.0-1.0")

    # -- constructors ----------------------------------------------------

    @classmethod
    def from_int(cls, value: int) -> Color:
        return cls((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)

    @classmethod
    def from_floats(cls, r: float, g: float, b: float, a: float | None = None) -> Color:
        """Build from 0.0-1.0 components, as stored in iTerm2 plists."""
        conv = lambda f: max(0, min(255, round(float(f) * 255)))  # noqa: E731
        return cls(conv(r), conv(g), conv(b), a)

    # -- renderers -------------------------------------------------------

    @property
    def hex(self) -> str:
        """`#rrggbb` — the spelling almost every terminal format wants."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @property
    def hex_bare(self) -> str:
        """`rrggbb`, no leading hash (ghostty, Xresources shorthand)."""
        return f"{self.r:02x}{self.g:02x}{self.b:02x}"

    @property
    def rgb_triple(self) -> str:
        """`r,g,b` in decimal (konsole)."""
        return f"{self.r},{self.g},{self.b}"

    @property
    def floats(self) -> tuple[float, float, float]:
        return (self.r / 255, self.g / 255, self.b / 255)

    def __str__(self) -> str:
        return self.hex


# Ordered most- to least-specific so that e.g. `rgb:` never falls through to
# the bare-hex branch.
_RE_HASH_HEX = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_RE_0X_HEX = re.compile(r"^0[xX]([0-9a-fA-F]{6,8})$")
_RE_BARE_HEX = re.compile(r"^([0-9a-fA-F]{6})$")
# X11 `rgb:RR/GG/BB`, where each component is 1-4 hex digits scaled to 8 bits.
_RE_X11_RGB = re.compile(r"^rgb:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})$")
_RE_CSS_RGB = re.compile(
    r"^rgba?\(\s*([0-9]{1,3})\s*[,\s]\s*([0-9]{1,3})\s*[,\s]\s*([0-9]{1,3})"
    r"\s*(?:[,/]\s*([0-9]*\.?[0-9]+)\s*%?\s*)?\)$"
)
_RE_DEC_TRIPLE = re.compile(r"^([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})$")


def _expand_hex(digits: str) -> Color:
    n = len(digits)
    if n == 3:  # #rgb -> #rrggbb
        return Color(*(int(d * 2, 16) for d in digits))
    if n == 4:  # #rgba
        r, g, b, a = (int(d * 2, 16) for d in digits)
        return Color(r, g, b, a / 255)
    if n == 6:
        return Color(int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
    if n == 8:
        # Ambiguous in the wild: Windows Terminal writes #rrggbbaa, some tools
        # write #aarrggbb. rrggbbaa is the CSS reading and by far the commoner
        # one in terminal configs, so that is what we take.
        return Color(
            int(digits[0:2], 16),
            int(digits[2:4], 16),
            int(digits[4:6], 16),
            int(digits[6:8], 16) / 255,
        )
    raise ColorParseError(f"hex color must have 3, 4, 6, or 8 digits, got {n}")


def _scale_x11(component: str) -> int:
    """Scale a 1-4 hex-digit X11 component down to 8 bits."""
    value = int(component, 16)
    width = len(component) * 4
    # Replicate the high bits so that e.g. `f` -> 255 and `ffff` -> 255.
    return round(value * 255 / ((1 << width) - 1))


def parse_color(raw: str | int | float | None) -> Color | None:
    """Parse any spelling a terminal config might use. `None` passes through.

    Accepts: `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`, `0xrrggbb`, bare
    `rrggbb`, X11 `rgb:rr/gg/bb`, CSS `rgb()`/`rgba()`, decimal `r,g,b`
    triples, and CSS/X11 color names.
    """
    if raw is None:
        return None
    if isinstance(raw, Color):
        return raw
    if isinstance(raw, int):
        return Color.from_int(raw)

    text = str(raw).strip()
    if not text:
        return None
    # Strip quotes left over from formats we scan textually rather than parse.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if not text:
        return None

    if m := _RE_HASH_HEX.match(text):
        return _expand_hex(m.group(1))
    if m := _RE_0X_HEX.match(text):
        return _expand_hex(m.group(1))
    if m := _RE_X11_RGB.match(text):
        return Color(*(_scale_x11(c) for c in m.groups()))
    if m := _RE_CSS_RGB.match(text):
        r, g, b, a = m.groups()
        alpha = float(a) if a is not None else None
        if alpha is not None and alpha > 1.0:  # `rgb(... / 50%)` style
            alpha /= 100.0
        return Color(int(r), int(g), int(b), alpha)
    if m := _RE_DEC_TRIPLE.match(text):
        return Color(*(int(c) for c in m.groups()))
    if m := _RE_BARE_HEX.match(text):
        return _expand_hex(m.group(1))

    named = _NAMED.get(text.lower().replace(" ", ""))
    if named is not None:
        return Color.from_int(named)

    raise ColorParseError(f"unrecognised color: {raw!r}")
