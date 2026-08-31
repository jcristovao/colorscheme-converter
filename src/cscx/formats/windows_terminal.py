"""Windows Terminal — a JSON scheme object, standalone or inside settings.json."""

from __future__ import annotations

import json
import re
from typing import Any

from ..color import ColorParseError, parse_color
from ..palette import Palette, ANSI_NAMES, ansi_index
from ._util import decode

NAME = "windows-terminal"
ALIASES = ("windowsterminal", "wt")
EXTENSIONS = (".json",)
BINARY = False

# Windows Terminal says `purple` where the ANSI slot is magenta; `ansi_index`
# already knows that alias.
_SLOT_KEYS = ANSI_NAMES + ("purple",)

_SCALARS = {
    "background": "background",
    "foreground": "foreground",
    "cursorColor": "cursor",
    "selectionBackground": "selection_background",
}


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data).lstrip()
    if not text.startswith(("{", "[")):
        return 0.0
    try:
        json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        # `[Background]` opens a konsole scheme, not a JSON array.
        return 0.0
    if '"schemes"' in text:
        return 0.95
    if re.search(r'"brightBlack"\s*:', text):
        return 0.9
    if re.search(r'"cursorColor"\s*:', text):
        return 0.7
    return 0.1


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    scheme = _locate_scheme(document)
    if scheme is None:
        raise ValueError("no color scheme object found in this JSON")

    palette = Palette(name=scheme.get("name") or name, source_format=NAME)

    for key, attribute in _SCALARS.items():
        setattr(palette, attribute, _color(scheme.get(key)))

    for key in _SLOT_KEYS:
        palette.set_ansi(ansi_index(key), _color(scheme.get(key)))
        bright_key = "bright" + key[0].upper() + key[1:]
        palette.set_ansi(ansi_index(key, bright=True), _color(scheme.get(bright_key)))

    return palette


def _locate_scheme(document: Any) -> dict[str, Any] | None:
    """Find the scheme object, whether given bare, in a list, or in settings.json."""
    if isinstance(document, dict):
        if isinstance(schemes := document.get("schemes"), list):
            return _locate_scheme(schemes)
        if any(k in document for k in ("brightBlack", "cursorColor", "background")):
            return document
        return None
    if isinstance(document, list):
        for entry in document:
            if isinstance(entry, dict) and (found := _locate_scheme(entry)):
                return found
    return None


def _color(value: Any):
    try:
        return parse_color(value)
    except ColorParseError:
        return None
