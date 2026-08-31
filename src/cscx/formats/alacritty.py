"""alacritty — TOML today, YAML before 0.13. Both share one key structure."""

from __future__ import annotations

import re
import tomllib
from typing import Any

from ..color import ColorParseError, parse_color
from ..palette import Palette, ANSI_NAMES
from ._util import decode

NAME = "alacritty"
ALIASES = ("alacritty-toml", "alacritty-yaml", "alacritty-yml")
EXTENSIONS = (".toml", ".yml", ".yaml")
BINARY = False


def detect(data: bytes | str, filename: str | None = None) -> float:
    text = decode(data)
    stem = (filename or "").lower()

    if re.search(r"(?m)^\s*\[colors\.\w+", text):
        # wezterm also nests under [colors]; its array keys tell them apart.
        if re.search(r"(?m)^\s*(ansi|brights)\s*=\s*\[", text):
            return 0.2
        return 0.9

    if re.search(r"(?m)^\s*\[colors\]", text):
        if re.search(r"(?m)^\s*(ansi|brights)\s*=\s*\[", text):
            return 0.2
        # A bare [colors] is also how foot.ini opens. Only alacritty's own
        # keys settle it; without one this is a weak guess, not a match.
        if re.search(
            r"(?m)^\s*(draw_bold_text_with_bright_colors|dim_foreground|"
            r"bright_foreground|indexed_colors|vi_mode_cursor|footer_bar|"
            r"transparent_background_colors)\s*=",
            text,
        ):
            return 0.85
        return 0.3

    if re.search(r"(?m)^colors:\s*$", text) and re.search(
        r"(?m)^\s+(primary|normal|bright|cursor|selection):\s*$", text
    ):
        return 0.9

    if stem.startswith("alacritty."):
        return 0.5
    return 0.0


def parse(data: bytes | str, name: str | None = None) -> Palette:
    text = decode(data)
    if re.search(r"(?m)^\s*\[colors(\.\w+)*\]", text) or "=" in text.split("\n", 1)[0]:
        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            document = _parse_yaml_subset(text)
    else:
        document = _parse_yaml_subset(text)

    colors = document.get("colors") or {}
    palette = _from_mapping(colors, name=name)

    if isinstance(document.get("general"), dict):
        imports = document["general"].get("import")
        if imports:
            # Signals that the visible colors may live in an imported file.
            palette.extras.setdefault("alacritty", {})["import"] = imports
    return palette


def _from_mapping(colors: dict[str, Any], name: str | None) -> Palette:
    palette = Palette(name=name, source_format=NAME)

    primary = _section(colors, "primary")
    palette.background = _color(primary.get("background"))
    palette.foreground = _color(primary.get("foreground"))
    palette.dim_foreground = _color(primary.get("dim_foreground"))
    palette.bright_foreground = _color(primary.get("bright_foreground"))

    cursor = _section(colors, "cursor")
    palette.cursor = _color(cursor.get("cursor"))
    # alacritty calls the under-cursor glyph color `text`.
    palette.cursor_text = _color(cursor.get("text"))

    selection = _section(colors, "selection")
    palette.selection_background = _color(selection.get("background"))
    palette.selection_foreground = _color(selection.get("text"))

    for group, bright in (("normal", False), ("bright", True)):
        section = _section(colors, group)
        for slot in ANSI_NAMES:
            palette.set_named(slot, _color(section.get(slot)), bright=bright)

    dim = _section(colors, "dim")
    for index, slot in enumerate(ANSI_NAMES):
        palette.dim[index] = _color(dim.get(slot))

    for entry in colors.get("indexed_colors") or []:
        if isinstance(entry, dict) and "index" in entry:
            try:
                palette.set_indexed(int(entry["index"]), _color(entry.get("color")))
            except (ValueError, TypeError, IndexError):
                continue

    # Colors alacritty defines that the canonical model has no slot for.
    for group in ("vi_mode_cursor", "search", "hints", "footer_bar", "line_indicator"):
        if section := colors.get(group):
            palette.extras.setdefault("alacritty", {})[group] = section

    return palette


def _section(colors: dict[str, Any], key: str) -> dict[str, Any]:
    value = colors.get(key)
    return value if isinstance(value, dict) else {}


def _color(value: Any):
    try:
        return parse_color(value)
    except ColorParseError:
        return None


# -- minimal YAML ---------------------------------------------------------
#
# Pulling in PyYAML for pre-0.13 configs would cost the project its only
# dependency. Alacritty's colors block is a plain indented map of scalars
# plus one list of inline maps, so a small scanner covers it exactly.

_RE_INLINE_MAP = re.compile(r"^-\s*\{(.*)\}\s*$")


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    # Stack of (indent, container) with the document root at indent -1.
    stack: list[tuple[int, Any]] = [(-1, root)]

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]

        if m := _RE_INLINE_MAP.match(line):
            if isinstance(container, list):
                container.append(_parse_inline_map(m.group(1)))
            continue

        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), _strip_comment(value.strip())

        if not isinstance(container, dict):
            continue
        if value:
            container[key] = value
        else:
            # An empty value opens either a nested map or a list; we do not
            # know which until the next line, so guess by the key name.
            child: Any = [] if key.endswith("_colors") else {}
            container[key] = child
            stack.append((indent, child))

    return root


def _parse_inline_map(body: str) -> dict[str, str]:
    entry: dict[str, str] = {}
    for part in body.split(","):
        key, sep, value = part.partition(":")
        if sep:
            entry[key.strip()] = value.strip().strip("'\"")
    return entry


def _strip_comment(value: str) -> str:
    """Drop a trailing `# ...` comment, leaving quoted hex values intact."""
    if value.startswith(("'", '"')):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
    head = value.split("#", 1)[0].strip() if not value.startswith("#") else value
    return head.strip().strip("'\"")
