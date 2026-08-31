"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .formats import PARSERS, detect_format, get_parser, parse_file
from .palette import Palette, ANSI_NAMES


def _format_names() -> list[str]:
    return sorted({parser.NAME for parser in PARSERS.values()})


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
    return 2


def _cmd_formats() -> int:
    seen: dict[str, list[str]] = {}
    for alias, parser in PARSERS.items():
        seen.setdefault(parser.NAME, [])
        if alias != parser.NAME:
            seen[parser.NAME].append(alias)
    for name in sorted(seen):
        aliases = ", ".join(sorted(seen[name]))
        extensions = " ".join(get_parser(name).EXTENSIONS)
        print(f"{name:18} {extensions:24} {'aliases: ' + aliases if aliases else ''}".rstrip())
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
