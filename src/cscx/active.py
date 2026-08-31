"""Work out which scheme each application is currently using.

Two different problems wearing one name.

Terminals have no query interface, so their configuration is read and the
result resolved to an actual file -- which means the answer can be parsed and
shown as colors. Reading it correctly matters more than it sounds: kitty and
foot both apply directives in order, so a config with inline colors *and* an
include has a winner that a naive grep gets wrong.

Editors are asked directly. `nvim --headless -c 'lua print(vim.g.colors_name)'`
is authoritative in a way grepping an init file is not, because it accounts for
plugins and conditionals. What comes back is only a name: an editor theme
cannot be read back into sixteen ANSI slots, which is exactly why editors are
write-only elsewhere in this package.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ._text import strip_jsonc
from .palette import Palette

__all__ = ["Active", "detect", "detect_one", "TERMINALS", "EDITORS"]

#: How long to let an editor start up before giving up on it.
TIMEOUT = 20


@dataclass(frozen=True, slots=True)
class Active:
    """What one application is currently themed with."""

    app: str
    kind: str
    #: The scheme's name, or None when nothing is set.
    name: str | None
    #: The file it resolves to, where one could be found. Terminals only.
    path: Path | None = None
    #: How the answer was reached, for the sceptical.
    source: str = ""
    #: Ambiguity worth stating rather than papering over.
    note: str = ""

    @property
    def display(self) -> str:
        return self.name or "(default)"


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


def _run(command: list[str]) -> str | None:
    """Run a command, returning its stdout, or None if it failed."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


# -- terminals ------------------------------------------------------------


def _last_directive(text: str, config_dir: Path) -> tuple[Path | None, bool]:
    """Find the winning colour source in a kitty/foot style config.

    Returns the included file that wins, and whether inline colour
    definitions come after it. Order is what decides: both formats apply
    directives top to bottom, so the last one to set a colour wins.
    """
    include = re.compile(r"^\s*include\s*=?\s*(.+?)\s*$")
    inline = re.compile(
        r"^\s*(color\d{1,3}|background|foreground|regular\d|bright\d)\s*=?\s+?\S"
    )

    winner: Path | None = None
    winner_line = -1
    last_inline = -1

    for number, line in enumerate(text.splitlines()):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if match := include.match(line):
            candidate = match.group(1).strip()
            resolved = Path(candidate).expanduser()
            if not resolved.is_absolute():
                resolved = config_dir / candidate
            if resolved.is_file():
                winner, winner_line = resolved, number
        elif inline.match(line):
            last_inline = number

    return winner, last_inline > winner_line


def _kitty() -> Active:
    config = _config_home() / "kitty/kitty.conf"
    if not config.is_file():
        return Active("kitty", "terminal", None, source="no kitty.conf")

    included, inline_wins = _last_directive(config.read_text(), config.parent)
    if included is not None and not inline_wins:
        return Active("kitty", "terminal", included.stem, included,
                      f"include in {config.name}")
    note = ("colours are also set inline, after the include, so the inline "
            "values win" if included is not None else "")
    return Active("kitty", "terminal", "(inline)", config,
                  f"colours set directly in {config.name}", note)


def _foot() -> Active:
    config = _config_home() / "foot/foot.ini"
    if not config.is_file():
        return Active("foot", "terminal", None, source="no foot.ini")

    included, inline_wins = _last_directive(config.read_text(), config.parent)
    if included is not None and not inline_wins:
        return Active("foot", "terminal", included.stem, included,
                      f"last include in {config.name}")
    return Active("foot", "terminal", "(inline)", config,
                  f"[colors] in {config.name}")


def _alacritty() -> Active:
    config = _config_home() / "alacritty/alacritty.toml"
    if not config.is_file():
        return Active("alacritty", "terminal", None, source="no alacritty.toml")

    try:
        document = tomllib.loads(config.read_text())
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return Active("alacritty", "terminal", None, source=f"unreadable: {exc}")

    imports = (document.get("general") or {}).get("import") or []
    for entry in reversed([Path(str(i)).expanduser() for i in imports]):
        resolved = entry if entry.is_absolute() else config.parent / entry
        if resolved.is_file():
            return Active("alacritty", "terminal", resolved.stem, resolved,
                          "general.import")

    if document.get("colors"):
        return Active("alacritty", "terminal", "(inline)", config,
                      "[colors] in alacritty.toml")
    return Active("alacritty", "terminal", None, source="no theme imported")


def _ghostty() -> Active:
    config = _config_home() / "ghostty/config"
    if not config.is_file():
        return Active("ghostty", "terminal", None, source="no ghostty config")

    theme = None
    for line in config.read_text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        if (match := re.match(r"^\s*theme\s*=\s*(.+?)\s*$", line)):
            theme = match.group(1)

    if theme is None:
        return Active("ghostty", "terminal", "(inline)", config, "palette in config")

    for directory in (_config_home() / "ghostty/themes", Path("/usr/share/ghostty/themes")):
        if (candidate := directory / theme).is_file():
            return Active("ghostty", "terminal", theme, candidate, "theme =")
    return Active("ghostty", "terminal", theme, None, "theme =",
                  "the named theme file was not found")


def _konsole() -> list[Active]:
    """konsole themes per profile, so there may be several answers."""
    profiles = sorted((_data_home() / "konsole").glob("*.profile"))
    if not profiles:
        return [Active("konsole", "terminal", None, source="no profiles")]

    default = _konsole_default()
    results = []
    for profile in profiles:
        scheme = None
        for line in profile.read_text().splitlines():
            if line.startswith("ColorScheme="):
                scheme = line.split("=", 1)[1].strip()
        if scheme is None:
            continue

        path = None
        for directory in (_data_home() / "konsole", Path("/usr/share/konsole")):
            if (candidate := directory / f"{scheme}.colorscheme").is_file():
                path = candidate
                break

        is_default = default is not None and profile.name == default
        note = "" if default is None else ("default profile" if is_default else "")
        results.append(Active(
            "konsole", "terminal", scheme, path, f"profile {profile.stem}", note
        ))

    if default is None and len(results) > 1:
        results = [
            Active(r.app, r.kind, r.name, r.path, r.source,
                   "konsolerc names no default profile, so which one applies "
                   "depends on how konsole was started")
            for r in results
        ]
    return results or [Active("konsole", "terminal", None, source="no scheme set")]


def _konsole_default() -> str | None:
    konsolerc = _config_home() / "konsolerc"
    if not konsolerc.is_file():
        return None
    for line in konsolerc.read_text().splitlines():
        if line.startswith("DefaultProfile="):
            return line.split("=", 1)[1].strip()
    return None


def _xresources() -> Active:
    """X resources are queried live, so this is the merged current state."""
    if not shutil.which("xrdb"):
        return Active("xresources", "terminal", None, source="xrdb not installed")
    output = _run(["xrdb", "-query"])
    if not output or "color0" not in output:
        return Active("xresources", "terminal", None, source="no colours loaded")
    return Active("xresources", "terminal", "(loaded)", None, "xrdb -query")


# -- editors --------------------------------------------------------------


def _vim(binary: str, app: str) -> Active:
    if not shutil.which(binary):
        return Active(app, "editor", None, source=f"{binary} not installed")

    if app == "neovim":
        output = _run([
            binary, "--headless",
            "-c", 'lua io.write(tostring(vim.g.colors_name or ""))',
            "-c", "qa!",
        ])
        # neovim writes headless output to stderr, so ask for it explicitly.
        if output is None:
            output = _neovim_fallback(binary)
    else:
        output = _vimscript_name(binary)

    name = (output or "").strip() or None
    if name in {"nil", "v:null", ""}:
        name = None
    return Active(app, "editor", name, None, f"asked {binary}")


def _neovim_fallback(binary: str) -> str | None:
    try:
        result = subprocess.run(
            [binary, "--headless",
             "-c", 'lua io.stderr:write(tostring(vim.g.colors_name or ""))',
             "-c", "qa!"],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stderr


def _vimscript_name(binary: str) -> str | None:
    """Ask vim for `g:colors_name` via a redirect, which -es can report."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        sink = Path(directory) / "name"
        try:
            subprocess.run(
                [binary, "-es", "--not-a-term",
                 "-c", f"redir! > {sink}",
                 "-c", 'silent echo get(g:, "colors_name", "")',
                 "-c", "redir END", "-c", "qa!"],
                capture_output=True, text=True, timeout=TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return sink.read_text() if sink.is_file() else None


def _helix() -> Active:
    config = _config_home() / "helix/config.toml"
    if not config.is_file():
        return Active("helix", "editor", None, source="no helix config")
    try:
        theme = tomllib.loads(config.read_text()).get("theme")
    except (tomllib.TOMLDecodeError, OSError):
        theme = None
    return Active("helix", "editor", theme, None, "theme in config.toml")


def _emacs() -> Active:
    """Read the init file rather than starting Emacs.

    `emacs --batch` with a user init is slow and can hang on a prompt, which
    is a poor trade for a status line.
    """
    candidates = [
        _config_home() / "emacs/init.el",
        Path.home() / ".emacs.d/init.el",
        Path.home() / ".emacs",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        if match := re.search(r"\(load-theme\s+'([\w-]+)", text):
            return Active("emacs", "editor", match.group(1), None, f"{path.name}")
        if match := re.search(r"custom-enabled-themes\s*'?\(([\w\s-]+)\)", text):
            return Active("emacs", "editor", match.group(1).split()[0], None,
                          f"{path.name}")
    return Active("emacs", "editor", None, source="no theme found in init")


#: VS Code and its forks keep user settings in the same place, per app.
_VSCODE_DIRS = {
    "vscode": ("Code", "Code - OSS", "VSCodium"),
    "cursor": ("Cursor",),
    "antigravity": ("Antigravity",),
}


def _vscode(app: str) -> Active:
    for directory in _VSCODE_DIRS[app]:
        settings = _config_home() / directory / "User/settings.json"
        if not settings.is_file():
            continue
        # Settings are JSON with comments, which json cannot parse directly.
        try:
            document = json.loads(strip_jsonc(settings.read_text(errors="replace")))
            theme = document.get("workbench.colorTheme")
        except ValueError as exc:
            return Active(app, "editor", None, None,
                          f"{directory}/User/settings.json",
                          f"settings.json could not be parsed: {exc}")
        return Active(app, "editor", theme, None, f"{directory}/User/settings.json")
    return Active(app, "editor", None, source="not configured")


# -- registry -------------------------------------------------------------

TERMINALS = ("kitty", "alacritty", "foot", "ghostty", "konsole", "xresources")
EDITORS = ("vim", "neovim", "helix", "emacs", "vscode", "cursor", "antigravity")

_DETECTORS = {
    "kitty": _kitty,
    "alacritty": _alacritty,
    "foot": _foot,
    "ghostty": _ghostty,
    "konsole": _konsole,
    "xresources": _xresources,
    "vim": lambda: _vim("vim", "vim"),
    "neovim": lambda: _vim("nvim", "neovim"),
    "helix": _helix,
    "emacs": _emacs,
    "vscode": lambda: _vscode("vscode"),
    "cursor": lambda: _vscode("cursor"),
    "antigravity": lambda: _vscode("antigravity"),
}


def detect_one(app: str) -> list[Active]:
    """What `app` is themed with. A list, because konsole answers per profile."""
    if app not in _DETECTORS:
        raise KeyError(f"unknown application {app!r}")
    try:
        result = _DETECTORS[app]()
    except Exception as exc:                 # never let one probe sink the rest
        return [Active(app, "terminal" if app in TERMINALS else "editor",
                       None, source=f"probe failed: {exc}")]
    return result if isinstance(result, list) else [result]


def detect(*, terminals: bool = True, editors: bool = True) -> list[Active]:
    """Everything currently themed, skipping applications that are absent.

    `editors=False` avoids starting vim and neovim, which is what a caller
    wants when it only needs file paths to match against.
    """
    apps: list[str] = []
    if terminals:
        apps += list(TERMINALS)
    if editors:
        apps += list(EDITORS)

    found: list[Active] = []
    for app in apps:
        found.extend(entry for entry in detect_one(app) if _worth_showing(entry))
    return found


def _worth_showing(entry: Active) -> bool:
    """Hide applications that simply are not here."""
    absent = ("not installed", "not configured", "no ")
    return entry.name is not None or not entry.source.startswith(absent)


def palette_of(entry: Active) -> Palette | None:
    """Parse the scheme an entry points at, when it points at one."""
    if entry.path is None:
        return None
    from .formats import parse_file

    try:
        return parse_file(entry.path)
    except Exception:
        return None
