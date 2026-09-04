"""Optional overrides for the judgement calls in the editor mapping.

Nothing here is required. With no file present the built-in defaults apply,
which is what every generated theme has used so far. The file is never
written for you: `cscx mapping --dump` prints it on request, and `activate`
remains the only part of cscx that puts anything in a config directory.

An *overlay*, deliberately, rather than a generated copy of the defaults. A
dumped default freezes at the version that wrote it, so a later fix to a
mapping would be silently shadowed by a stale file -- the same drift that has
already caught this project more than once. Writing only what you want changed
means everything else keeps tracking the code.

What is exposed here is taste: which ANSI hue each base16 accent takes, how
far the derived UI shades step, how readable comments must be. What is *not*
exposed is anything specifying another program's interface -- Claude Code's
token names, VS Code's colour keys, Helix's scopes. Those are not preferences,
and a wrong value in one produces a theme that loads and silently does
nothing.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

__all__ = [
    "Mapping",
    "MappingError",
    "DEFAULT",
    "load",
    "config_path",
    "dump",
    "reset_cache",
]


class MappingError(ValueError):
    """Raised when an override file cannot be used as written."""


#: The accent roles. base00 and base05 are the background and foreground, and
#: base01-base04, base06 and base07 are the derived ramp, so neither is an
#: ANSI slot anybody can reassign.
ACCENT_ROLES = ("base08", "base09", "base0A", "base0B", "base0C", "base0D",
                "base0E", "base0F")

#: Ramp positions, as a fraction of the way from background to foreground.
RAMP_KEYS = ("base01", "base02", "base04", "base06", "base07")


@dataclass(frozen=True, slots=True)
class Mapping:
    """The tunable half of the editor mapping."""

    #: Accent role -> ANSI slot. A role absent here keeps its derived default:
    #: base09 and base0F have no ANSI hue of their own and are blended.
    accents: dict[str, int] = field(default_factory=dict)
    #: How far each derived shade steps. base01/base02/base04 run from the
    #: background toward the foreground; base06/base07 continue past it.
    ramp: dict[str, float] = field(default_factory=dict)
    #: Minimum contrast for comments against the background.
    comment_contrast: float = 4.5
    #: The window the comment search may move within.
    comment_floor: float = 0.45
    comment_ceiling: float = 0.85
    #: Where this came from, for `cscx mapping` to report.
    source: Path | None = None

    def accent(self, role: str, default: int | None) -> int | None:
        return self.accents.get(role, default)

    def step(self, role: str, default: float) -> float:
        return self.ramp.get(role, default)


#: What applies when there is no file, which is the normal case.
DEFAULT = Mapping(
    accents={"base08": 1, "base0A": 3, "base0B": 2, "base0C": 6,
             "base0D": 4, "base0E": 5},
    ramp={"base01": 0.10, "base02": 0.22, "base04": 0.72,
          "base06": 0.25, "base07": 0.50},
)


def config_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(root) / "cscx/mapping.toml"


_cache: Mapping | None = None


def reset_cache() -> None:
    """Forget the loaded file. Tests and `--check` need a clean read."""
    global _cache
    _cache = None


def load(path: Path | None = None, *, use_cache: bool = True) -> Mapping:
    """The effective mapping: the defaults, with any overrides applied.

    Reading is cached, because `derive` is called once per generated theme and
    a browse session generates a great many.
    """
    global _cache
    if path is None and use_cache and _cache is not None:
        return _cache

    target = path or config_path()
    result = DEFAULT if not target.is_file() else _merge(DEFAULT, _read(target))

    if path is None and use_cache:
        _cache = result
    return result


def _read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise MappingError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise MappingError(f"{path} could not be read: {exc}") from exc


def _merge(base: Mapping, document: dict) -> Mapping:
    """Apply an override document, rejecting anything it cannot mean.

    Errors here are loud on purpose. A mistyped role name that was quietly
    ignored would leave someone staring at a theme that did not change, with
    nothing to tell them why.
    """
    if unknown := set(document) - {"roles", "ramp"}:
        raise MappingError(
            f"unknown section(s): {', '.join(sorted(unknown))}; "
            f"expected [roles] and [ramp]"
        )

    accents = dict(base.accents)
    for role, slot in (document.get("roles") or {}).items():
        if role not in ACCENT_ROLES:
            raise MappingError(
                f"[roles] {role}: not an accent role; "
                f"expected one of {', '.join(ACCENT_ROLES)}"
            )
        if not isinstance(slot, int) or isinstance(slot, bool) or not 0 <= slot <= 15:
            raise MappingError(f"[roles] {role} = {slot!r}: expected an ANSI slot 0-15")
        accents[role] = slot

    ramp = dict(base.ramp)
    contrast, floor, ceiling = (
        base.comment_contrast, base.comment_floor, base.comment_ceiling
    )
    scalars = {"comment_contrast", "comment_floor", "comment_ceiling"}

    for key, value in (document.get("ramp") or {}).items():
        if key not in RAMP_KEYS and key not in scalars:
            raise MappingError(
                f"[ramp] {key}: unknown; expected one of "
                f"{', '.join((*RAMP_KEYS, *sorted(scalars)))}"
            )
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise MappingError(f"[ramp] {key} = {value!r}: expected a number")

        if key == "comment_contrast":
            if not 0 <= value <= 21:
                raise MappingError(
                    f"[ramp] comment_contrast = {value}: a WCAG ratio runs 1 to 21"
                )
            contrast = float(value)
        elif key == "comment_floor":
            floor = float(value)
        elif key == "comment_ceiling":
            ceiling = float(value)
        else:
            if not 0.0 <= value <= 1.0:
                raise MappingError(
                    f"[ramp] {key} = {value}: expected a fraction between 0.0 and 1.0"
                )
            ramp[key] = float(value)

    for name, value in (("comment_floor", floor), ("comment_ceiling", ceiling)):
        if not 0.0 <= value <= 1.0:
            raise MappingError(
                f"[ramp] {name} = {value}: expected a fraction between 0.0 and 1.0"
            )
    if floor > ceiling:
        raise MappingError(
            f"[ramp] comment_floor ({floor}) is above comment_ceiling ({ceiling}), "
            f"leaving no range to search"
        )

    return replace(
        base, accents=accents, ramp=ramp,
        comment_contrast=contrast, comment_floor=floor, comment_ceiling=ceiling,
    )


#: Only these two are blended rather than taken from a slot, so the dump has
#: to say so instead of printing a number that was never used.
_BLENDED = {"base09": "50% color1 -> color3", "base0F": "25% color1 -> color3"}


def dump(mapping: Mapping | None = None) -> str:
    """The effective mapping as TOML, to copy from. Never written for you."""
    current = mapping or load()
    lines = [
        "# cscx mapping overrides. Everything here is optional: delete a line",
        "# and the built-in default applies again. Write only what you change,",
        "# so the rest keeps tracking the code.",
        "",
        "[roles]",
        "# base16 accent role -> ANSI slot (0-15).",
    ]
    for role in ACCENT_ROLES:
        if (slot := current.accents.get(role)) is not None:
            lines.append(f"{role} = {slot}")
        else:
            lines.append(f"# {role} = <slot>    # default: {_BLENDED[role]}")

    lines += [
        "",
        "[ramp]",
        "# How far each derived shade steps, as a fraction from background",
        "# toward foreground. base06 and base07 continue past the foreground.",
    ]
    for key in RAMP_KEYS:
        lines.append(f"{key} = {current.ramp[key]}")

    lines += [
        "",
        "# Comments must clear this contrast ratio against the background,",
        "# searched between floor and ceiling. The ceiling matters: without it",
        "# a low-contrast scheme puts comments on top of normal text.",
        f"comment_contrast = {current.comment_contrast}",
        f"comment_floor = {current.comment_floor}",
        f"comment_ceiling = {current.comment_ceiling}",
    ]
    return "\n".join(lines) + "\n"
