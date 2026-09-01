"""Read neovim colorschemes back into palettes, by asking neovim.

This is the one place the "editors are write-only" rule bends, and it bends
for a specific reason: the rule is about *parsing theme files*, which remains
hopeless -- a colorscheme is a program, not a table of colors. But neovim can
be asked to load one and report what it resolved to, which is both easier and
more reliable than parsing ever was.

Two tiers, and which one applied is recorded rather than hidden:

  exact    the colorscheme sets `terminal_color_0..15`, so the sixteen ANSI
           colors come straight from its author. 169 of 179 schemes on the
           machine this was written on do this.
  derived  it does not, so the palette is inferred from semantic highlight
           groups -- String is green, Function is blue, Keyword is magenta.
           That is the inverse of the base16 mapping used to write themes,
           and it is an approximation.

Every scheme is loaded inside a single neovim process, because starting one
per scheme would turn eleven seconds into several minutes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .color import Color, is_dark, mix, parse_color
from .palette import Palette

__all__ = [
    "NvimUnavailable",
    "available",
    "extract",
    "cache_dir",
    "export",
]

#: Loading 179 schemes takes about eleven seconds, so allow generous headroom.
TIMEOUT = 300


class NvimUnavailable(RuntimeError):
    """Raised when neovim is not installed or would not answer."""


def cache_dir() -> Path:
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "cscx/nvim"


# The semantic groups worth reading. Order matters within each tuple: the
# first group that resolves to a colour wins.
_DERIVED_SLOTS = (
    (1, ("DiagnosticError", "ErrorMsg")),        # red
    (2, ("String",)),                            # green
    (3, ("Type", "DiagnosticWarn", "WarningMsg")),  # yellow
    (4, ("Function", "Identifier")),             # blue
    (5, ("Keyword", "Statement")),               # magenta
    (6, ("Special", "DiagnosticHint", "Constant")),  # cyan
)

_LUA = r"""
local names = vim.fn.getcompletion("", "color")
local wanted = vim.g.cscx_only
if wanted and #wanted > 0 then
  local keep, set = {}, {}
  for _, n in ipairs(wanted) do set[n] = true end
  for _, n in ipairs(names) do if set[n] then keep[#keep + 1] = n end end
  names = keep
end

local groups = {
  "Normal", "Comment", "String", "Constant", "Function", "Identifier",
  "Keyword", "Statement", "Type", "Special", "ErrorMsg", "WarningMsg",
  "DiagnosticError", "DiagnosticWarn", "DiagnosticInfo", "DiagnosticHint",
  "Visual", "Cursor", "CursorLine", "NonText",
}

local function hex(value)
  return value and string.format("#%06x", value) or nil
end

local out = {}
for _, name in ipairs(names) do
  -- terminal_color_* survives a colorscheme change unless cleared, so the
  -- previous scheme's palette would otherwise leak into the next one.
  for i = 0, 15 do vim.g["terminal_color_" .. i] = nil end

  local ok = pcall(function() vim.cmd.colorscheme(name) end)
  if ok then
    local terminal = {}
    for i = 0, 15 do terminal[i + 1] = vim.g["terminal_color_" .. i] end

    local resolved = {}
    for _, group in ipairs(groups) do
      local h = vim.api.nvim_get_hl(0, { name = group, link = false })
      resolved[group] = { fg = hex(h.fg), bg = hex(h.bg) }
    end

    out[#out + 1] = {
      name = name,
      background = vim.o.background,
      terminal = terminal,
      groups = resolved,
    }
  end
end
io.stderr:write(vim.json.encode(out))
"""


def available() -> list[str]:
    """Every colorscheme this neovim can load, plugins included."""
    binary = shutil.which("nvim")
    if binary is None:
        raise NvimUnavailable("neovim is not installed")

    result = _run([
        binary, "--headless",
        "-c", 'lua io.stderr:write(table.concat(vim.fn.getcompletion("", "color"), "\\n"))',
        "-c", "qa!",
    ])
    return [line.strip() for line in result.splitlines() if line.strip()]


def _run(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT
        )
    except FileNotFoundError as exc:
        raise NvimUnavailable("neovim is not installed") from exc
    except subprocess.SubprocessError as exc:
        raise NvimUnavailable(f"neovim did not answer: {exc}") from exc
    # Headless neovim writes to stderr, which is where the payload lands.
    return completed.stderr


@dataclass(frozen=True, slots=True)
class Extracted:
    """One colorscheme, as a palette plus how it was obtained."""

    name: str
    palette: Palette
    exact: bool


def extract(only: list[str] | None = None) -> list[Extracted]:
    """Load colorschemes in one neovim process and read their colors back."""
    binary = shutil.which("nvim")
    if binary is None:
        raise NvimUnavailable("neovim is not installed")

    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "extract.lua"
        script.write_text(_LUA)
        command = [binary, "--headless"]
        if only:
            command += ["-c", f"let g:cscx_only = {json.dumps(only)}"]
        command += ["-c", f"luafile {script}", "-c", "qa!"]
        payload = _run(command)

    start = payload.find("[")
    if start == -1:
        raise NvimUnavailable("neovim returned nothing to read")
    try:
        entries = json.loads(payload[start:])
    except ValueError as exc:
        raise NvimUnavailable(f"could not read neovim's answer: {exc}") from exc

    return [built for entry in entries if (built := _build(entry)) is not None]


def _build(entry: dict) -> Extracted | None:
    name = entry.get("name")
    groups = entry.get("groups") or {}
    normal = groups.get("Normal") or {}

    palette = Palette(name=name, source_format="neovim")
    palette.background = _color(normal.get("bg"))
    palette.foreground = _color(normal.get("fg"))

    terminal = [_color(value) for value in (entry.get("terminal") or [])]
    exact = len(terminal) == 16 and all(color is not None for color in terminal)

    if exact:
        for index, color in enumerate(terminal):
            palette.set_ansi(index, color)
    elif not _derive(palette, groups):
        return None

    palette.cursor = _color((groups.get("Cursor") or {}).get("bg"))
    palette.cursor_text = _color((groups.get("Cursor") or {}).get("fg"))
    palette.selection_background = _color((groups.get("Visual") or {}).get("bg"))
    palette.selection_foreground = _color((groups.get("Visual") or {}).get("fg"))

    palette.extras["neovim"] = {
        "colorscheme": name,
        "palette": "exact" if exact else "derived",
        "background": entry.get("background"),
    }
    return Extracted(name, palette, exact)


def _derive(palette: Palette, groups: dict) -> bool:
    """Infer sixteen slots from semantic highlight groups.

    The inverse of the mapping used to write editor themes: whatever paints
    strings is green, whatever paints functions is blue, and so on.
    """
    background, foreground = palette.background, palette.foreground
    if background is None or foreground is None:
        return False

    dark = is_dark(background)
    extreme = Color(255, 255, 255) if dark else Color(0, 0, 0)

    # black and white anchor the ramp; the shades between come from the
    # background, since no highlight group carries them.
    palette.set_ansi(0, _color((groups.get("CursorLine") or {}).get("bg"))
                     or mix(background, foreground, 0.12))
    palette.set_ansi(7, foreground)

    for index, candidates in _DERIVED_SLOTS:
        for group in candidates:
            if (color := _color((groups.get(group) or {}).get("fg"))) is not None:
                palette.set_ansi(index, color)
                break

    if any(palette.ansi[i] is None for i in range(8)):
        return False

    # Bright variants are a step toward the extreme, which is what most
    # schemes do by hand anyway.
    for index in range(8):
        palette.set_ansi(index + 8, mix(palette.ansi[index], extreme, 0.20))
    return True


def _color(value) -> Color | None:
    if not value:
        return None
    try:
        return parse_color(value)
    except Exception:
        return None


def export(directory: Path | None = None, only: list[str] | None = None) -> list[Path]:
    """Write every colorscheme out as a kitty-format file.

    kitty's format is used as the container because it holds a full palette
    losslessly and every other part of cscx already reads it -- which makes
    these themes browsable, previewable and convertible with no special case
    anywhere else.
    """
    from .emitters import get_emitter

    target = directory or cache_dir()
    target.mkdir(parents=True, exist_ok=True)

    written = []
    for item in extract(only):
        body = get_emitter("kitty").emit(item.palette, None)
        note = (
            f"# neovim colorscheme: {item.name}\n"
            f"# palette: {'exact (terminal_color_*)' if item.exact else 'derived from highlight groups'}\n"
        )
        path = target / f"{_safe(item.name)}.conf"
        path.write_text(note + body)
        written.append(path)
    return written


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)
