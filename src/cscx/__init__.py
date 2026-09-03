"""cscx — convert terminal color schemes between formats via one palette."""

from .color import Color, ColorParseError, parse_color
from .palette import Palette
from .fill import fill
from .formats import PARSERS, detect_format, get_parser, parse_file
from .emitters import EMITTERS, emit, get_emitter

__version__ = "0.11.0"

__all__ = [
    "Color",
    "ColorParseError",
    "EMITTERS",
    "PARSERS",
    "Palette",
    "detect_format",
    "emit",
    "fill",
    "get_emitter",
    "get_parser",
    "parse_color",
    "parse_file",
    "__version__",
]
