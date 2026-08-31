"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .editors import (
    CONTRAST_TARGET,
    EDITORS,
    EditorPaletteError,
    get_editor,
    theme_warnings,
)
from .emitters import EMITTERS, get_emitter
from .fill import fill
from .formats import PARSERS, detect_format, get_parser, parse_file
from .palette import Palette, ANSI_NAMES


def _format_names() -> list[str]:
    """Formats that can be read. Editors are write-only."""
    return sorted({parser.NAME for parser in PARSERS.values()})


def _target_names() -> list[str]:
    """Everything that can be written: terminal formats plus editors."""
    return sorted(set(EMITTERS) | set(EDITORS))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cscx",
        description="Read a terminal color scheme into a format-neutral palette.",
    )
    parser.add_argument("--version", action="version", version=f"cscx {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read = subparsers.add_parser("parse", help="parse a scheme and show it")
    read.add_argument("path", type=Path, help="scheme or config file to read")
    read.add_argument(
        "-f", "--from", dest="source_format", choices=_format_names(),
        help="skip detection and parse as this format",
    )
    read.add_argument("--json", action="store_true", help="emit the palette as JSON")
    read.add_argument(
        "--no-color", action="store_true", help="skip the terminal swatches",
    )

    sniff = subparsers.add_parser("detect", help="report which format a file looks like")
    sniff.add_argument("path", type=Path)
    sniff.add_argument("--json", action="store_true")

    convert = subparsers.add_parser("convert", help="convert a scheme to another format")
    convert.add_argument("path", type=Path, help="scheme or config file to read")
    convert.add_argument(
        "-t", "--to", dest="target", required=True, metavar="FORMAT",
        help="output format or editor, or 'all' to write every target",
    )
    convert.add_argument(
        "-f", "--from", dest="source_format", choices=_format_names(),
        help="skip detection and parse as this format",
    )
    convert.add_argument(
        "-o", "--output", type=Path,
        help="write here instead of stdout; a directory when --to all",
    )
    convert.add_argument(
        "--fill", action="store_true",
        help="derive values the source omitted (cursor=fg, selection=inverse, "
             "bright=normal) and mark each one as derived",
    )
    convert.add_argument(
        "--terminal-exact", action="store_true",
        help="editors only: use just the 16 palette colors, deriving no UI shades",
    )
    convert.add_argument(
        "--contrast", type=float, default=None, metavar="RATIO",
        help="editors only: minimum contrast for comments against the background "
             "(default 4.5, WCAG AA); 0 disables the check",
    )
    convert.add_argument("--name", help="override the scheme name")

    subparsers.add_parser("formats", help="list supported formats")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    match args.command:
        case "formats":
            return _cmd_formats()
        case "detect":
            return _cmd_detect(args)
        case "parse":
            return _cmd_parse(args)
        case "convert":
            return _cmd_convert(args)
    return 2


def _cmd_formats() -> int:
    seen: dict[str, list[str]] = {}
    for alias, parser in PARSERS.items():
        seen.setdefault(parser.NAME, [])
        if alias != parser.NAME:
            seen[parser.NAME].append(alias)
    print("terminal formats (read and written)")
    for name in sorted(seen):
        aliases = ", ".join(sorted(seen[name]))
        extensions = " ".join(get_parser(name).EXTENSIONS)
        print(f"  {name:18} {extensions:24} "
              f"{'aliases: ' + aliases if aliases else ''}".rstrip())

    print()
    print("editors (written only)")
    for name in sorted(EDITORS):
        editor = get_editor(name)
        print(f"  {name:18} {editor.EXTENSION:24} {editor.INSTALL_PATH.format(name='NAME')}")
    return 0


def _cmd_detect(args: argparse.Namespace) -> int:
    try:
        raw = args.path.read_bytes()
    except OSError as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    ranked = detect_format(raw, args.path.name)
    if args.json:
        print(json.dumps([{"format": n, "confidence": round(s, 3)} for n, s in ranked], indent=2))
    elif not ranked:
        print("no format matched", file=sys.stderr)
    else:
        for name, score in ranked:
            print(f"{score:5.2f}  {name}")
    return 0 if ranked else 1


def _cmd_parse(args: argparse.Namespace) -> int:
    try:
        palette = parse_file(args.path, format=args.source_format)
    except (OSError, ValueError, KeyError) as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(palette.to_dict(), indent=2))
    else:
        use_color = not args.no_color and sys.stdout.isatty()
        print(render(palette, color=use_color))

    if gaps := palette.missing():
        print(f"cscx: {len(gaps)} value(s) not set: {', '.join(gaps)}", file=sys.stderr)
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    try:
        palette = parse_file(args.path, format=args.source_format)
    except (OSError, ValueError, KeyError) as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    if args.name:
        palette.name = args.name

    derived = {}
    if args.fill:
        palette, derived = fill(palette)

    targets = _target_names() if args.target == "all" else [args.target]
    try:
        writers = [_writer(t, args, derived) for t in targets]
    except KeyError as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    if args.target == "all":
        if args.output is None:
            print("cscx: --to all needs -o DIRECTORY", file=sys.stderr)
            return 1
        return _write_all(palette, writers, args.output)

    name, _filename, binary, render = writers[0]
    try:
        rendered = render(palette)
    except EditorPaletteError as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    _report_gaps(palette, derived, is_editor=name in EDITORS)
    if name in EDITORS:
        _report_theme_warnings(palette, args)

    if args.output is None:
        if binary:
            sys.stdout.buffer.write(rendered)
        else:
            sys.stdout.write(rendered)
        return 0

    _write(args.output, rendered)
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


def _writer(target: str, args: argparse.Namespace, derived: dict):
    """Resolve a target name to `(name, extension, binary, render)`.

    Terminal emitters and editor writers take different arguments, so they are
    wrapped into one shape here rather than complicating either protocol.
    """
    if target in EDITORS:
        editor = get_editor(target)
        return (
            editor.NAME,
            editor.FILENAME,
            editor.BINARY,
            lambda palette: editor.emit(
                palette,
                terminal_exact=args.terminal_exact,
                contrast_target=(
                    CONTRAST_TARGET if args.contrast is None else args.contrast
                ),
            ),
        )
    emitter = get_emitter(target)
    return (
        emitter.NAME,
        f"{{name}}.{emitter.NAME}{emitter.EXTENSION}",
        emitter.BINARY,
        lambda palette: emitter.emit(palette, derived),
    )


def _write_all(palette, writers, directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    # Editors are not free to pick a filename: Emacs only finds a theme named
    # `NAME-theme.el`, and VS Code expects `NAME-color-theme.json`.
    stem = _slug(palette)
    failures = 0
    written: dict[Path, tuple[str, bytes]] = {}

    for name, filename, _binary, render in writers:
        target = directory / filename.format(name=stem)
        try:
            rendered = render(palette)
        except EditorPaletteError as exc:
            print(f"cscx: skipped {name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        # Forks of the same editor produce the same file under the same name.
        # Writing it repeatedly would be silent self-overwriting, so say so,
        # and compare the content rather than assuming it matches.
        payload = rendered if isinstance(rendered, bytes) else rendered.encode()
        if (previous := written.get(target)) is not None:
            owner, existing = previous
            note = "identical" if existing == payload else "DIFFERENT CONTENT"
            print(f"cscx: {name} shares {target.name} with {owner} ({note})",
                  file=sys.stderr)
            continue

        _write(target, rendered)
        written[target] = (name, payload)
        print(f"wrote {target}", file=sys.stderr)
    return 1 if failures else 0


def _slug(palette) -> str:
    from .editors._common import slug

    return slug(palette.name)


def _report_theme_warnings(palette, args: argparse.Namespace) -> None:
    """Editor caveats, on stderr as well as in the file where one is possible."""
    try:
        warnings = theme_warnings(
            palette,
            terminal_exact=args.terminal_exact,
            contrast_target=CONTRAST_TARGET if args.contrast is None else args.contrast,
        )
    except EditorPaletteError:
        return
    for warning in warnings:
        print(f"cscx: {warning}", file=sys.stderr)


def _write(path: Path, rendered: str | bytes) -> None:
    if isinstance(rendered, bytes):
        path.write_bytes(rendered)
    else:
        path.write_text(rendered)


def _report_gaps(palette: Palette, derived: dict, *, is_editor: bool = False) -> None:
    """Say on stderr what was derived, and what stayed unset."""
    if derived:
        print(f"cscx: derived {len(derived)} value(s): "
              f"{', '.join(sorted(derived))}", file=sys.stderr)
    if gaps := palette.missing():
        # An editor theme cannot be produced at all with gaps, so it never
        # reaches here; for terminal formats the keys are simply left out.
        print(f"cscx: {len(gaps)} value(s) unset and omitted from the output: "
              f"{', '.join(gaps)}", file=sys.stderr)


def _swatch(color, width: int = 4) -> str:
    if color is None:
        return " " * width
    return f"\x1b[48;2;{color.r};{color.g};{color.b}m{' ' * width}\x1b[0m"


def render(palette: Palette, *, color: bool = True) -> str:
    """A human-readable summary, with true-color swatches when useful."""
    lines = [
        f"name          {palette.name or '-'}",
        f"source format {palette.source_format or '-'}",
        "",
    ]

    def row(label: str, value) -> str:
        swatch = _swatch(value) + " " if color else ""
        return f"  {label:<22}{swatch}{value.hex if value else '-'}"

    lines.append("base")
    for label, attribute in (
        ("background", "background"),
        ("foreground", "foreground"),
        ("cursor", "cursor"),
        ("cursor text", "cursor_text"),
        ("selection background", "selection_background"),
        ("selection foreground", "selection_foreground"),
    ):
        lines.append(row(label, getattr(palette, attribute)))

    lines.append("")
    lines.append("ansi")
    for index, slot in enumerate(ANSI_NAMES):
        normal, bright = palette.ansi[index], palette.ansi[index + 8]
        normal_cell = (_swatch(normal) + " " if color else "") + (normal.hex if normal else "-" * 7)
        bright_cell = (_swatch(bright) + " " if color else "") + (bright.hex if bright else "-" * 7)
        lines.append(f"  {slot:<10}{index:>3} {normal_cell}   {index + 8:>3} {bright_cell}")

    if any(c is not None for c in palette.dim):
        lines.append("")
        lines.append("dim")
        for index, slot in enumerate(ANSI_NAMES):
            lines.append(row(slot, palette.dim[index]))

    if palette.indexed:
        lines.append("")
        lines.append(f"indexed       {len(palette.indexed)} extra slot(s) "
                     f"({min(palette.indexed)}-{max(palette.indexed)})")

    if palette.extras:
        lines.append("")
        lines.append("extras")
        for source, values in palette.extras.items():
            lines.append(f"  {source}: {json.dumps(values, default=str)}")

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
