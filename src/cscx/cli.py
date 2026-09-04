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

    browse = subparsers.add_parser(
        "browse", help="browse, preview and copy the schemes on this machine"
    )
    browse.add_argument(
        "-p", "--path", type=Path, action="append", default=[], metavar="PATH",
        help="also search this file or directory; repeatable",
    )

    preview = subparsers.add_parser("preview", help="show one scheme as colors")
    preview.add_argument("path", type=Path)
    preview.add_argument(
        "-f", "--from", dest="source_format", choices=_format_names(),
        help="skip detection and parse as this format",
    )
    preview.add_argument("--width", type=int, default=76)

    listing = subparsers.add_parser("list", help="list the schemes found on this machine")
    listing.add_argument(
        "query", nargs="*", default=[], metavar="QUERY",
        help="fuzzy filter; `source:neovim` or `format:kitty` narrows a field",
    )
    listing.add_argument(
        "-p", "--path", type=Path, action="append", default=[], metavar="PATH",
        help="also search this file or directory; repeatable",
    )
    listing.add_argument("--json", action="store_true")

    activate = subparsers.add_parser(
        "activate", help="install a scheme into an application's configuration"
    )
    activate.add_argument("path", type=Path, help="scheme to install")
    activate.add_argument(
        "-a", "--for", dest="app", required=True, metavar="APP",
        help="application to configure",
    )
    activate.add_argument(
        "-f", "--from", dest="source_format", choices=_format_names(),
        help="skip detection and parse as this format",
    )
    activate.add_argument("--name", help="override the theme name")
    activate.add_argument(
        "--profile", type=Path,
        help="konsole only: the .profile to point at the scheme",
    )
    activate.add_argument(
        "-n", "--dry-run", action="store_true",
        help="print what would change and stop",
    )
    activate.add_argument(
        "-y", "--yes", action="store_true", help="do not ask for confirmation",
    )
    activate.add_argument(
        "--no-backup", action="store_true",
        help="do not copy existing files aside first",
    )
    activate.add_argument(
        "--no-validate", action="store_true",
        help="skip asking the application whether it accepts the result",
    )

    live = subparsers.add_parser(
        "live", help="recolour the running terminal, without changing any config"
    )
    live.add_argument("path", type=Path, nargs="?", help="scheme to apply")
    live.add_argument(
        "-f", "--from", dest="source_format", choices=_format_names(),
        help="skip detection and parse as this format",
    )
    live.add_argument(
        "--reset", action="store_true", help="restore the terminal's own colours",
    )

    active = subparsers.add_parser(
        "active", help="show which scheme each application is currently using"
    )
    active.add_argument(
        "--no-editors", action="store_true",
        help="skip the editors, which have to be started to be asked",
    )
    active.add_argument("--json", action="store_true")

    nvim = subparsers.add_parser(
        "nvim-themes",
        help="read neovim's colorschemes into palettes you can browse and convert",
    )
    nvim.add_argument(
        "--list", action="store_true", help="just list the colorschemes available",
    )
    nvim.add_argument(
        "-o", "--output", type=Path,
        help="write here instead of the cache under ~/.cache/cscx/nvim",
    )
    nvim.add_argument(
        "--only", action="append", default=[], metavar="NAME",
        help="export just this colorscheme; repeatable",
    )

    mapping = subparsers.add_parser(
        "mapping",
        help="show or check the optional overrides for the editor mapping",
    )
    mapping.add_argument(
        "--dump", action="store_true",
        help="print the effective mapping as TOML, to copy from",
    )
    mapping.add_argument(
        "--check", action="store_true",
        help="validate the override file and say nothing if it is fine",
    )
    mapping.add_argument(
        "--path", type=Path, metavar="FILE",
        help="use this file instead of ~/.config/cscx/mapping.toml",
    )

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
        case "browse":
            return _cmd_browse(args)
        case "preview":
            return _cmd_preview(args)
        case "list":
            return _cmd_list(args)
        case "activate":
            return _cmd_activate(args)
        case "live":
            return _cmd_live(args)
        case "active":
            return _cmd_active(args)
        case "nvim-themes":
            return _cmd_nvim_themes(args)
        case "mapping":
            return _cmd_mapping(args)
    return 2


def _cmd_mapping(args: argparse.Namespace) -> int:
    from .mapping import (
        ACCENT_ROLES,
        MappingError,
        config_path,
        dump,
        load,
    )

    target = args.path or config_path()
    try:
        effective = load(args.path, use_cache=False)
    except MappingError as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if not target.is_file():
            print(f"cscx: no override file at {target}; the defaults apply",
                  file=sys.stderr)
        return 0

    if args.dump:
        print(dump(effective), end="")
        if args.path is None:
            print(f"\ncscx: nothing was written; save this to {target} to use it",
                  file=sys.stderr)
        return 0

    print(f"override file  {target}"
          f"{'' if target.is_file() else '   (absent, defaults apply)'}")
    print()
    print("roles          base16 accent -> ANSI slot")
    for role in ACCENT_ROLES:
        slot = effective.accents.get(role)
        shown = f"color{slot}" if slot is not None else "blended from color1/color3"
        print(f"  {role:8}     {shown}")
    print()
    print("ramp           fraction from background toward foreground")
    for key, value in effective.ramp.items():
        print(f"  {key:8}     {value}")
    print(f"  comments     {effective.comment_contrast}:1 minimum, searched "
          f"{effective.comment_floor}-{effective.comment_ceiling}")
    print()
    print("cscx mapping --dump  prints this as TOML to copy from",
          file=sys.stderr)
    return 0


def _cmd_nvim_themes(args: argparse.Namespace) -> int:
    from .nvim_themes import NvimUnavailable, available, cache_dir, export

    try:
        if args.list:
            for name in available():
                print(name)
            return 0

        target = args.output or cache_dir()
        print(f"cscx: asking neovim to load its colorschemes (this takes a moment)",
              file=sys.stderr)
        written = export(target, args.only or None)
    except NvimUnavailable as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    print(f"cscx: wrote {len(written)} colorschemes to {target}", file=sys.stderr)
    if args.output is None:
        print("cscx: they now show up in `cscx browse` and `cscx list`",
              file=sys.stderr)
    return 0


def _cmd_active(args: argparse.Namespace) -> int:
    from .active import detect, palette_of
    from .preview import swatch_strip

    found = detect(editors=not args.no_editors)
    if args.json:
        print(json.dumps([
            {"app": a.app, "kind": a.kind, "scheme": a.name,
             "path": str(a.path) if a.path else None,
             "source": a.source, "note": a.note or None}
            for a in found
        ], indent=2))
        return 0

    if not found:
        print("cscx: nothing found", file=sys.stderr)
        return 1

    show_colors = sys.stdout.isatty()
    for entry in found:
        swatch = ""
        if show_colors and (palette := palette_of(entry)) is not None:
            swatch = swatch_strip(palette, width=1) + "  "
        print(f"{entry.app:12} {swatch}{entry.display:34} {entry.source}")
        if entry.note:
            print(f"{'':12} note: {entry.note}")

    if any(e.kind == "editor" and e.name for e in found):
        print("\ncscx: editor schemes are names only; an editor theme cannot be "
              "read back into a palette", file=sys.stderr)
    return 0


def _cmd_activate(args: argparse.Namespace) -> int:
    from .activation import ActivationError, apply_plan, plan

    try:
        palette = parse_file(args.path, format=args.source_format)
        proposed = plan(palette, args.app, name=args.name, profile=args.profile)
    except (OSError, ValueError, KeyError, ActivationError) as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    print(proposed.describe())

    if args.dry_run:
        print("\n(dry run; nothing was changed)", file=sys.stderr)
        return 0

    edits = [step for step in proposed.steps if step.edits_existing]
    if edits and not args.yes and sys.stdin.isatty():
        # Only existing files are worth stopping for; creating a theme file
        # alongside is not the part anyone needs to think about.
        listed = ", ".join(str(step.path) for step in edits)
        answer = input(f"\nedit {listed}? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("cscx: nothing was changed", file=sys.stderr)
            return 1

    try:
        backups = apply_plan(
            proposed, backup=not args.no_backup, validate=not args.no_validate
        )
    except ActivationError as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        print("cscx: nothing was changed; every file was restored", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    for backup in backups:
        print(f"backed up {backup}", file=sys.stderr)
    if proposed.reload:
        print(f"reload with: {proposed.reload}", file=sys.stderr)
    return 0


def _cmd_live(args: argparse.Namespace) -> int:
    from . import live

    if args.reset:
        if not live.reset():
            print("cscx: no terminal to write to", file=sys.stderr)
            return 1
        return 0

    if args.path is None:
        print("cscx: live needs a scheme, or --reset", file=sys.stderr)
        return 2

    try:
        palette = parse_file(args.path, format=args.source_format)
    except (OSError, ValueError, KeyError) as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1

    if not live.is_supported():
        print("cscx: no terminal here to recolour", file=sys.stderr)
        return 1
    if not live.apply(palette):
        print("cscx: could not write to the terminal", file=sys.stderr)
        return 1

    print("cscx: applied to this terminal; `cscx live --reset` restores it",
          file=sys.stderr)
    return 0


def _cmd_browse(args: argparse.Namespace) -> int:
    try:
        from .tui import run
    except ImportError:
        print(
            "cscx: browse needs Textual, which is an optional dependency.\n"
            "      install it with: pip install 'cscx[tui]'",
            file=sys.stderr,
        )
        return 1
    return run(args.path)


def _cmd_preview(args: argparse.Namespace) -> int:
    from .preview import render

    try:
        palette = parse_file(args.path, format=args.source_format)
    except (OSError, ValueError, KeyError) as exc:
        print(f"cscx: {exc}", file=sys.stderr)
        return 1
    print(render(palette, width=args.width))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    from .discovery import discover, filter_schemes

    found = discover(args.path)
    if query := " ".join(args.query):
        found = filter_schemes(query, found)
    if args.json:
        print(json.dumps([
            {"path": str(d.path), "format": d.format, "source": d.source,
             "confidence": round(d.confidence, 3), "origin": d.origin, "name": d.name}
            for d in found
        ], indent=2))
        return 0

    if not found:
        print("cscx: no schemes found", file=sys.stderr)
        return 1
    for entry in found:
        print(f"{entry.source:12} {entry.name:34} {entry.path}")
    print(f"\n{len(found)} schemes", file=sys.stderr)
    return 0


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
                contrast_target=args.contrast,
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
            contrast_target=args.contrast,
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
