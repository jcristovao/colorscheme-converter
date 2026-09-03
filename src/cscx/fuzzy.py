"""Fuzzy matching for the scheme filter.

A plain substring test is too strict once there are several hundred schemes
with names like `base16-atelier-sulphurpool-light`: nobody wants to type that,
and `b16sulph` should find it. This is the usual subsequence match with
scoring, small enough to keep in the package rather than take a dependency
for.

Scoring favours, in order: an exact substring, matches that start a word, and
runs of adjacent characters. That is what makes `gruv` rank plain `gruvbox`
above `base16-gruvbox-dark-soft`, and `nvim` rank a neovim scheme above one
whose name merely contains those letters scattered about.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

__all__ = ["score", "matches", "rank"]

T = TypeVar("T")

#: Characters after which the next character begins a new "word".
_BOUNDARIES = frozenset(" -_./:()[]")

_SUBSTRING_BASE = 1000
_CHAR = 10
_ADJACENT = 15
_WORD_START = 20
_GAP_PENALTY = 1
_MAX_GAP_PENALTY = 40


def score(query: str, text: str) -> int | None:
    """How well `query` matches `text`, or None if it does not match at all.

    Higher is better. Scores are only comparable between candidates for the
    same query.
    """
    if not query:
        return 0
    needle, haystack = query.lower(), text.lower()

    if (position := haystack.find(needle)) != -1:
        # An exact substring always beats a scattered match. Prefer one that
        # starts a word, then one that starts earlier.
        bonus = _WORD_START if _starts_word(haystack, position) else 0
        return _SUBSTRING_BASE + bonus + max(0, 100 - position)

    return _subsequence(needle, haystack)


def _subsequence(needle: str, haystack: str) -> int | None:
    total = 0
    index = 0
    previous = -1

    for char in needle:
        found = haystack.find(char, index)
        if found == -1:
            return None

        total += _CHAR
        if found == previous + 1:
            total += _ADJACENT
        if _starts_word(haystack, found):
            total += _WORD_START

        gap = found - (previous + 1)
        total -= min(gap * _GAP_PENALTY, _MAX_GAP_PENALTY)

        previous = found
        index = found + 1

    return total


def _starts_word(text: str, position: int) -> bool:
    return position == 0 or text[position - 1] in _BOUNDARIES


def matches(query: str, text: str) -> bool:
    """Whether `query` matches `text` at all."""
    return score(query, text) is not None


def rank(
    query: str, items: Iterable[T], key: Callable[[T], str]
) -> list[T]:
    """Keep the items matching `query`, best first.

    Ties keep the input order, so an unfiltered list stays in whatever order
    the caller sorted it into.
    """
    if not query:
        return list(items)

    scored = []
    for position, item in enumerate(items):
        if (value := score(query, key(item))) is not None:
            scored.append((-value, position, item))
    scored.sort()
    return [item for _, _, item in scored]
