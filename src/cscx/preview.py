"""Render a palette as something you can actually judge by eye.

Emitted as ANSI escapes rather than a widget tree, so the same renderer serves
the plain CLI and the TUI, and so this module keeps the package's zero
dependencies.

For terminals the preview is faithful rather than suggestive: a terminal
scheme *is* sixteen colors plus foreground and background, so a simulated
shell session shows exactly what the real one will look like. The code sample
is an approximation -- it paints a snippet with the base16 roles the editor
writers would use, which is the mapping, not the editor's own rendering.
"""

from __future__ import annotations

from .color import Color, contrast_ratio
from .editors.roles import EditorPaletteError, Roles, derive
from .fill import fill
from .palette import ANSI_NAMES, Palette

__all__ = ["render", "swatch_strip", "RESET"]

RESET = "\x1b[0m"


def _fg(color: Color | None) -> str:
    return "" if color is None else f"\x1b[38;2;{color.r};{color.g};{color.b}m"


def _bg(color: Color | None) -> str:
    return "" if color is None else f"\x1b[48;2;{color.r};{color.g};{color.b}m"


def _paint(text: str, fg: Color | None = None, bg: Color | None = None,
           bold: bool = False, italic: bool = False) -> str:
    prefix = f"{_bg(bg)}{_fg(fg)}"
    if bold:
        prefix += "\x1b[1m"
    if italic:
        prefix += "\x1b[3m"
    return f"{prefix}{text}{RESET}" if prefix else text


def swatch_strip(palette: Palette, width: int = 2) -> str:
    """A compact 16-block strip, for list rows and one-line summaries."""
    blocks = []
    for color in palette.ansi:
        blocks.append(_paint(" " * width, bg=color) if color else " " * width)
    return "".join(blocks)


def render(palette: Palette, *, width: int = 76) -> str:
    """A full preview: palette, a shell session, and a syntax sample."""
    sections = [
        _heading(palette),
        _palette_block(palette),
        _terminal_sample(palette, width),
    ]

    roles, note = _roles_for(palette)
    if roles is not None:
        sections.append(_code_sample(roles, width))
        sections.append(_notes(roles))
    elif note:
        sections.append([_paint(note, fg=palette.foreground)])

    lines: list[str] = []
    for section in sections:
        if section:
            lines.extend(section)
            lines.append("")
    return "\n".join(lines).rstrip("\n")


def _roles_for(palette: Palette) -> tuple[Roles | None, str]:
    """Derive roles for the syntax sample, filling gaps if that is enough."""
    try:
        return derive(palette), ""
    except EditorPaletteError:
        pass
    try:
        filled, _ = fill(palette)
        return derive(filled), ""
    except EditorPaletteError as exc:
        return None, f"no syntax preview: {exc}"


def _heading(palette: Palette) -> list[str]:
    name = palette.name or "(unnamed)"
    origin = palette.source_format or "unknown"
    line = _paint(f" {name} ", fg=palette.background, bg=palette.foreground, bold=True)
    return [f"{line} {_paint(origin, fg=palette.foreground)}"]


def _palette_block(palette: Palette) -> list[str]:
    """The sixteen slots, normal above bright, with their hex values."""
    lines = []
    for offset, label in ((0, "normal"), (8, "bright")):
        cells = []
        for index in range(8):
            color = palette.ansi[offset + index]
            cells.append(_paint("  ", bg=color) if color else "  ")
        swatches = " ".join(cells)
        names = " ".join(f"{n[:2]:2}" for n in ANSI_NAMES)
        lines.append(f"  {label:6} {swatches}   {_paint(names, fg=palette.foreground)}")

    for label, color in (("bg", palette.background), ("fg", palette.foreground),
                         ("cursor", palette.cursor), ("select", palette.selection_background)):
        if color is not None:
            lines.append(f"  {label:6} {_paint('  ', bg=color)}   "
                         f"{_paint(color.hex, fg=color)}")
    return lines


def _terminal_sample(palette: Palette, width: int) -> list[str]:
    """A shell session drawn in the scheme's own colors.

    Faithful, not suggestive: these are the exact colors the terminal will use.
    """
    bg, fg = palette.background, palette.foreground
    slot = palette.ansi

    def row(*parts: str) -> str:
        body = "".join(parts)
        # Pad within the background so the panel reads as a terminal window.
        visible = _visible_length(body)
        return f"{_bg(bg)}{body}{' ' * max(0, width - visible)}{RESET}"

    prompt = (_paint("joao", fg=slot[10] or fg, bold=True)
              + _paint("@", fg=fg) + _paint("arch", fg=slot[12] or fg, bold=True)
              + _paint(" ~/code ", fg=slot[11] or fg) + _paint("$ ", fg=fg))

    return [
        row(prompt, _paint("ls", fg=fg)),
        row(_paint("  README.md  ", fg=fg), _paint("src", fg=slot[12] or fg, bold=True),
            _paint("  ", fg=fg), _paint("tests", fg=slot[12] or fg, bold=True),
            _paint("  build.log", fg=slot[5] or fg)),
        row(prompt, _paint("git status --short", fg=fg)),
        row(_paint("   M ", fg=slot[11] or fg), _paint("src/cscx/color.py", fg=fg)),
        row(_paint("  ?? ", fg=slot[9] or fg), _paint("docs/", fg=fg)),
        row(prompt, _paint("pytest -q", fg=fg)),
        row(_paint("  ....", fg=slot[10] or fg), _paint("F", fg=slot[9] or fg, bold=True),
            _paint("...", fg=slot[10] or fg), _paint("  [100%]", fg=slot[8] or fg)),
        row(_paint("  FAILED", fg=slot[1] or fg, bold=True),
            _paint(" tests/test_color.py::test_hex", fg=fg)),
        row(_paint("  selected text", fg=palette.selection_foreground or bg,
                   bg=palette.selection_background or fg)),
    ]


#: The syntax sample, as (text, role) runs. Roles are base16 names, so this
#: shows the same mapping the editor writers use.
_SNIPPET: tuple[tuple[tuple[str, str], ...], ...] = (
    (("# derive the base16 roles from a terminal palette", "base03"),),
    (),
    (("def", "base0E"), (" ", "base05"), ("contrast", "base0D"), ("(", "base05"),
     ("a", "base08"), (": ", "base05"), ("Color", "base0A"), (", ", "base05"),
     ("b", "base08"), (": ", "base05"), ("Color", "base0A"), (") -> ", "base05"),
     ("float", "base0A"), (":", "base05")),
    (('    """WCAG contrast, 1.0 to 21.0."""', "base0B"),),
    (("    first", "base08"), (", ", "base05"), ("second", "base08"),
     (" = ", "base05"), ("luminance", "base0D"), ("(", "base05"), ("a", "base08"),
     ("), ", "base05"), ("luminance", "base0D"), ("(", "base05"), ("b", "base08"),
     (")", "base05")),
    (("    if", "base0E"), (" first ", "base08"), ("<", "base05"), (" second", "base08"),
     (":", "base05")),
    (("        first", "base08"), (", ", "base05"), ("second", "base08"),
     (" = second", "base08"), (", first", "base08")),
    (("    return", "base0E"), (" (first ", "base08"), ("+", "base05"),
     (" 0.05", "base09"), (") ", "base05"), ("/", "base05"), (" (second ", "base08"),
     ("+", "base05"), (" 0.05", "base09"), (")", "base05")),
)


def _code_sample(roles: Roles, width: int) -> list[str]:
    """A snippet painted with the base16 roles the editor writers assign."""
    background = roles["base00"]
    lines = []
    for run in _SNIPPET:
        body = "".join(
            _paint(text, fg=roles.slots.get(role), bg=background,
                   italic=(role == "base03"))
            for text, role in run
        )
        visible = _visible_length(body) + 2      # the two-space indent
        lines.append(f"{_bg(background)}  {body}{' ' * max(0, width - visible)}{RESET}")
    return lines


def _notes(roles: Roles) -> list[str]:
    ratio = contrast_ratio(roles["base03"], roles["base00"])
    verdict = "AA" if ratio >= 4.5 else ("AA large" if ratio >= 3.0 else "low")
    lines = [_paint(f"  comments {ratio:.1f}:1 vs background ({verdict})",
                    fg=roles["base04"])]
    for warning in roles.warnings:
        lines.append(_paint(f"  note: {warning}", fg=roles["base0A"]))
    return lines


def _visible_length(text: str) -> int:
    """Length ignoring ANSI escapes, for padding."""
    length, index = 0, 0
    while index < len(text):
        if text[index] == "\x1b":
            end = text.find("m", index)
            index = len(text) if end == -1 else end + 1
            continue
        length += 1
        index += 1
    return length
