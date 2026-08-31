"""Text hygiene for values that flow from a scheme into generated files.

A scheme name is attacker-adjacent data: it comes from a filename or from a
free-text field like konsole's `Description`, and it lands in comment lines
and quoted strings. A newline in it ends the comment early and turns the rest
into code, so it is flattened before use rather than trusted.
"""

from __future__ import annotations

import re

__all__ = ["single_line", "toml_string", "elisp_string", "strip_jsonc"]

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


def elisp_string(text: str | None) -> str:
    """Render `text` as an Emacs Lisp string literal."""
    escaped = single_line(text).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas from JSON-with-comments.

    String-aware, which a regex is not: VS Code settings routinely contain
    URLs like "file:///home/...", and a naive `//` strip truncates the line
    and leaves the document unparseable. The failure is silent -- the caller
    sees "no theme configured" rather than an error -- which is what makes it
    worth doing properly.
    """
    out: list[str] = []
    index, length = 0, len(text)

    while index < length:
        char = text[index]

        if char == '"':                      # copy the whole string literal
            out.append(char)
            index += 1
            while index < length:
                out.append(text[index])
                if text[index] == "\\":
                    index += 1
                    if index < length:
                        out.append(text[index])
                        index += 1
                    continue
                if text[index] == '"':
                    index += 1
                    break
                index += 1
            continue

        if char == "/" and index + 1 < length:
            if text[index + 1] == "/":
                index = text.find("\n", index)
                if index == -1:
                    break
                continue
            if text[index + 1] == "*":
                end = text.find("*/", index + 2)
                index = length if end == -1 else end + 2
                continue

        if char == ",":
            # A trailing comma is one followed only by whitespace and a close.
            look = index + 1
            while look < length and text[look] in " \t\r\n":
                look += 1
            if look < length and text[look] in "}]":
                index += 1
                continue

        out.append(char)
        index += 1

    return "".join(out)
