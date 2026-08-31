"""cscx — read terminal color schemes from any format into one canonical palette."""

from .color import Color, ColorParseError, parse_color
from .palette import Palette
from .formats import PARSERS, detect_format, get_parser, parse_file

__version__ = "0.1.0"

__all__ = [
    "Color",
    "ColorParseError",
    "Palette",
    "PARSERS",
    "detect_format",
    "get_parser",
    "parse_color",
    "parse_file",
    "__version__",
]
