"""Find the color schemes already installed on this machine.

Searching is deliberately narrow: an explicit table of the places each
application keeps its themes, rather than a walk of the home directory. Scheme
files have no distinguishing extension in several formats -- ghostty themes
have none at all -- so a broad sweep would mean sniffing thousands of
unrelated files to turn up a few hundred schemes.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .formats import detect_format
from .fuzzy import score

__all__ = [
    "Discovered",
    "tilde",
    "SearchLocation",
    "search_locations",
    "discover",
    "filter_schemes",
    "installed_applications",
]

#: Below this confidence a match is more likely an unrelated file that happens
#: to sit in a theme directory.
MIN_CONFIDENCE = 0.4

#: Nothing this large is a color scheme; skip it without reading.
MAX_SIZE = 1 << 20


def tilde(path: Path | str) -> str:
    """`path` with the home directory written as `~`.

    Cosmetic, but the places it is shown -- the browser's status line, the
    copy dialog's destination field -- are bounded by the terminal width, and
    `/home/somebody` is a prefix every single entry shares. Anything reading a
    value back must call `expanduser`, which is what the shell would have done.
    """
    home, text = str(Path.home()), str(path)
    if text == home:
        return "~"
    if text.startswith(home + "/"):
        return "~" + text[len(home):]
    return text


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


@dataclass(frozen=True, slots=True)
class SearchLocation:
    """One directory to look in, and what to expect there."""

    label: str
    root: Path
    patterns: tuple[str, ...]
    #: The format this directory is expected to hold. Detection still runs;
    #: this only breaks ties, since several formats share the `.toml` and
    #: `.conf` extensions.
    expect: str | None = None
    #: Which application these schemes came from. Not the same as the format:
    #: neovim colorschemes are cached as kitty files, and calling them "kitty"
    #: in a listing would be actively misleading.
    source: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            object.__setattr__(self, "source", self.label.split()[0].lower())


def search_locations() -> tuple[SearchLocation, ...]:
    """The places worth looking, resolved against the current environment."""
    config, data, home = _config_home(), _data_home(), Path.home()
    return (
        SearchLocation("kitty config", config / "kitty", ("*.conf",), "kitty"),
        SearchLocation("kitty themes", config / "kitty/themes", ("**/*.conf",), "kitty"),
        SearchLocation("kitty themes", config / "kitty/kitty-themes", ("**/*.conf",), "kitty"),
        SearchLocation("kitty themes", Path("/usr/share/kitty/themes"), ("**/*.conf",), "kitty"),

        SearchLocation("alacritty config", config / "alacritty", ("*.toml", "*.yml"), "alacritty"),
        SearchLocation("alacritty themes", config / "alacritty/themes",
                       ("**/*.toml", "**/*.yml"), "alacritty"),

        SearchLocation("ghostty config", config / "ghostty", ("config",), "ghostty"),
        SearchLocation("ghostty themes", config / "ghostty/themes", ("*",), "ghostty"),
        SearchLocation("ghostty themes", Path("/usr/share/ghostty/themes"), ("*",), "ghostty"),

        SearchLocation("konsole schemes", data / "konsole", ("*.colorscheme",), "konsole"),
        SearchLocation("konsole schemes", Path("/usr/share/konsole"), ("*.colorscheme",), "konsole"),

        SearchLocation("foot config", config / "foot", ("*.ini",), "foot"),
        SearchLocation("foot themes", config / "foot/themes", ("**/*",), "foot"),
        SearchLocation("foot themes", Path("/usr/share/foot/themes"), ("**/*",), "foot"),

        SearchLocation("wezterm colors", config / "wezterm/colors", ("**/*.toml",), "wezterm"),
        SearchLocation("wezterm colors", home / ".wezterm/colors", ("**/*.toml",), "wezterm"),

        SearchLocation("windows terminal", config / "windows-terminal", ("*.json",),
                       "windows-terminal", source="windows-terminal"),

        SearchLocation("X resources", home, (".Xresources", ".Xdefaults"), "xresources",
                       source="xresources"),
        SearchLocation("X resources", config / "X11", ("*",), "xresources",
                       source="xresources"),

        SearchLocation("iTerm2 schemes", config / "iterm2", ("**/*.itermcolors",), "iterm2",
                       source="iterm2"),
        SearchLocation("iTerm2 schemes", data / "iterm2", ("**/*.itermcolors",), "iterm2",
                       source="iterm2"),

        SearchLocation("KDE schemes", data / "color-schemes", ("*.colors",), "kde"),
        SearchLocation("KDE schemes", Path("/usr/share/color-schemes"),
                       ("*.colors",), "kde"),

        SearchLocation("cscx themes", config / "cscx/themes", ("**/*",), None),
        # Neovim colorschemes exported by `cscx nvim-themes`, stored in kitty
        # format because it holds a palette losslessly and everything here
        # already reads it.
        SearchLocation("neovim colorschemes", _nvim_cache(), ("*.conf",), "kitty"),
    )


def _nvim_cache() -> Path:
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "cscx/nvim"


@dataclass(frozen=True, slots=True)
class Discovered:
    """A scheme file found on disk."""

    path: Path
    format: str
    confidence: float
    origin: str
    #: The application this came from -- "neovim", not the "kitty" container
    #: its palette happens to be cached in.
    source: str = ""

    @property
    def haystack(self) -> str:
        """Everything a filter should be able to match against."""
        return f"{self.name} {self.source} {self.format} {self.origin}"

    @property
    def name(self) -> str:
        """A readable name: the filename without its extension."""
        stem = self.path.stem if self.path.suffix else self.path.name
        return stem.replace("_", " ").replace("-", " ").strip() or self.path.name

    @property
    def display_path(self) -> str:
        """The path, with the home directory written as `~`."""
        return tilde(self.path)

    @property
    def key(self) -> str:
        """Stable sort key: format first, then name."""
        return f"{self.format} {self.name.lower()}"


def discover(
    extra: Iterable[Path] = (),
    *,
    locations: Iterable[SearchLocation] | None = None,
    min_confidence: float = MIN_CONFIDENCE,
) -> list[Discovered]:
    """Find every scheme in the known locations, plus any `extra` paths.

    `extra` accepts files or directories; a directory is scanned one level
    deep, which is what pointing at a downloaded theme pack should mean.
    """
    found: dict[Path, Discovered] = {}
    search = tuple(search_locations() if locations is None else locations)

    for location in search:
        for path in _candidates(location):
            entry = _identify(path, location.expect, location.label,
                              min_confidence, location.source)
            if entry is not None:
                found.setdefault(entry.path, entry)

    for given in extra:
        given = Path(given).expanduser()
        try:
            paths = sorted(p for p in given.iterdir() if p.is_file()) \
                if given.is_dir() else [given]
        except OSError:
            continue
        for candidate in paths:
            entry = _identify(candidate, None, "given", min_confidence, "given")
            if entry is not None:
                found.setdefault(entry.path, entry)

    return sorted(found.values(), key=lambda d: d.key)


def _candidates(location: SearchLocation) -> Iterator[Path]:
    root = location.root.expanduser()
    if not root.is_dir():
        return
    for pattern in location.patterns:
        try:
            for path in sorted(root.glob(pattern)):
                if path.is_file():
                    yield path
        except OSError:
            continue


def _identify(
    path: Path,
    expect: str | None,
    origin: str,
    min_confidence: float,
    source: str = "",
) -> Discovered | None:
    try:
        if path.stat().st_size > MAX_SIZE:
            return None
        raw = path.read_bytes()
    except OSError:
        return None

    ranked = detect_format(raw, path.name)
    if not ranked:
        return None

    # Several formats share an extension, so a directory's expected format
    # wins over a marginally higher score from a lookalike.
    best_name, best_score = ranked[0]
    if expect is not None:
        for name, score in ranked:
            if name == expect and score >= min_confidence:
                best_name, best_score = name, score
                break

    if best_score < min_confidence:
        return None
    return Discovered(path.resolve(), best_name, best_score, origin,
                      source or best_name)


#: Binaries that indicate an application is actually installed.
_BINARIES = {
    "kitty": ("kitty",),
    "alacritty": ("alacritty",),
    "ghostty": ("ghostty",),
    "konsole": ("konsole",),
    "foot": ("foot",),
    "wezterm": ("wezterm",),
    "xresources": ("xrdb",),
    "kde": ("plasma-apply-colorscheme",),
    "vim": ("vim",),
    "neovim": ("nvim",),
    "helix": ("hx", "helix"),
    "emacs": ("emacs",),
    "vscode": ("code", "code-oss", "codium"),
    "cursor": ("cursor",),
    "antigravity": ("antigravity",),
    "ghostwriter": ("ghostwriter",),
}


def installed_applications() -> set[str]:
    """Which supported applications are actually present on this machine."""
    from shutil import which

    return {
        name for name, binaries in _BINARIES.items()
        if any(which(binary) for binary in binaries)
    }


#: `source:neovim` and friends, for narrowing without fuzz.
_FIELD = re.compile(r"^(source|src|format|fmt|origin)\s*:\s*(.*)$", re.I)
_ALIASES = {"src": "source", "fmt": "format"}


def filter_schemes(query: str, items: Iterable[Discovered]) -> list[Discovered]:
    """Narrow and rank `items` by `query`.

    A bare word is matched fuzzily against the name, source, format and
    origin together, so `neovim` finds every scheme read out of neovim and
    `b16sulph` finds base16-atelier-sulphurpool. A `source:`, `format:` or
    `origin:` prefix constrains that field exactly instead, which is what you
    want once you know the answer is "all the konsole ones".
    """
    constraints: list[tuple[str, str]] = []
    free: list[str] = []

    for term in query.split():
        if match := _FIELD.match(term):
            field = _ALIASES.get(match.group(1).lower(), match.group(1).lower())
            constraints.append((field, match.group(2).lower()))
        else:
            free.append(term)

    result = [
        item for item in items
        if all(value in getattr(item, field, "").lower() for field, value in constraints)
    ]
    if not free:
        return result

    # Every bare term has to match; the scores add up so a candidate matching
    # two terms well outranks one matching a single term brilliantly.
    ranked: list[tuple[int, int, Discovered]] = []
    for position, item in enumerate(result):
        total = 0
        for term in free:
            if (value := score(term, item.haystack)) is None:
                break
            total += value
        else:
            ranked.append((-total, position, item))

    ranked.sort()
    return [item for _, _, item in ranked]
