"""Text hygiene for values that flow from a scheme into generated files.

A scheme name is attacker-adjacent data: it comes from a filename or from a
free-text field like konsole's `Description`, and it lands in comment lines
and quoted strings. A newline in it ends the comment early and turns the rest
into code, so it is flattened before use rather than trusted.
"""

from __future__ import annotations

import re

__all__ = ["single_line", "toml_string"]

_WHITESPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def single_line(text: str | None, limit: int = 120) -> str:
    """Collapse `text` to one line of printable characters, truncated."""
    if not text:
        return ""
    flattened = _WHITESPACE.sub(" ", _CONTROL.sub(" ", str(text))).strip()
    return flattened[:limit].rstrip()


def toml_string(text: str | None) -> str:
    """Render `text` as a quoted TOML basic string, escaping what must be."""
    escaped = single_line(text).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
