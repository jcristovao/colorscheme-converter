"""Helpers shared by the line-oriented config parsers."""

from __future__ import annotations

from collections.abc import Iterator

__all__ = ["config_lines", "split_kv", "decode"]


def decode(data: bytes | str) -> str:
    """Decode source bytes, tolerating a BOM and stray non-UTF-8 bytes."""
    if isinstance(data, str):
        return data
    return data.decode("utf-8-sig", errors="replace")


def config_lines(text: str, comment_chars: str = "#") -> Iterator[tuple[int, str]]:
    """Yield `(lineno, line)` for meaningful lines, 1-indexed.

    Blank lines and whole-line comments are skipped. Trailing comments are
    deliberately *not* stripped: kitty and ghostty both treat `#` as a comment
    marker only at the start of a line, and stripping mid-line would corrupt
    hex colors.
    """
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line[0] in comment_chars:
            continue
        yield lineno, line


def split_kv(line: str, separators: str = "=") -> tuple[str, str] | None:
    """Split `key <sep> value` on the first separator, or on whitespace.

    Returns `None` when the line has no value part. An empty `separators`
    means "split on whitespace only", which is what kitty's format needs.
    """
    if separators:
        index = min(
            (i for i in (line.find(s) for s in separators) if i > 0),
            default=-1,
        )
        if index > 0:
            return line[:index].strip(), line[index + 1:].strip()
    parts = line.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None
