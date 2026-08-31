"""wezterm TOML color schemes — `ansi`/`brights` arrays under `[colors]`."""

from __future__ import annotations

import re
import tomllib
from typing import Any

from ..color import ColorParseError, parse_color
from ..palette import Palette
from ._util import decode

NAME = "wezterm"
ALIASES = ()
EXTENSIONS = (".toml",)
BINARY = False


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    has_arrays = re.search(r"(?m)^\s*(ansi|brights)\s*=\s*\[", text)
    if not has_arrays:
        return 0.0
    score = 0.85
    if re.search(r"(?m)^\s*\[metadata\]", text):
        score = 0.95
    return score


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"not valid TOML: {exc}") from exc

    colors = document.get("colors")
    colors = colors if isinstance(colors, dict) else {}
    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    palette = Palette(name=metadata.get("name") or name, source_format=NAME)

    palette.background = _color(colors.get("background"))
    palette.foreground = _color(colors.get("foreground"))
    palette.cursor = _color(colors.get("cursor_bg"))
    palette.cursor_text = _color(colors.get("cursor_fg"))
    palette.selection_background = _color(colors.get("selection_bg"))
    palette.selection_foreground = _color(colors.get("selection_fg"))

    for offset, key in ((0, "ansi"), (8, "brights")):
        values = colors.get(key)
        if isinstance(values, list):
            for slot, value in enumerate(values[:8]):
                palette.set_ansi(offset + slot, _color(value))

    indexed = colors.get("indexed")
    if isinstance(indexed, dict):
        for key, value in indexed.items():
            try:
                palette.set_indexed(int(key), _color(value))
            except (ValueError, IndexError):
                continue

    for key in ("cursor_border", "scrollbar_thumb", "split", "compose_cursor"):
        if (color := _color(colors.get(key))) is not None:
            palette.extras.setdefault("wezterm", {})[key] = color.hex
    if metadata:
        palette.extras.setdefault("wezterm", {})["metadata"] = metadata

    return palette


def _color(value: Any):
    try:
        return parse_color(value)
    except ColorParseError:
        return None
