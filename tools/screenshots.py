#!/usr/bin/env python3
"""Regenerate the SVG screenshots in `docs/img/`.

    $ python3 tools/screenshots.py

Two kinds of picture, both real output rather than a mock-up:

* the browser, captured through Textual's own `export_screenshot`
* the plain-terminal commands, whose ANSI output is re-rendered with Rich

Both run against a sandboxed `HOME` holding a small demo corpus, so the
pictures show `~/.config/kitty/themes/...` rather than whoever generated
them, and rerunning produces the same images on a different machine.

The corpus is built by converting a handful of schemes shipped in
`tests/fixtures` plus any of a named set found on this machine -- the colours
in the pictures are therefore real published schemes, not invented ones.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "docs" / "img"
FIXTURES = ROOT / "tests" / "fixtures"

#: Schemes to put in the demo corpus, if this machine has them. Chosen to be
#: recognisable and to differ from one another at a glance -- a screenshot of
#: eight variations on one palette shows nothing.
WANTED = (
    "nord", "dracula", "solarized_dark", "solarized_light", "tokyo_night",
    "catppuccin_mocha", "everforest_dark", "one_dark", "monokai", "ayu_dark",
    "papercolor_light", "rose_pine",
)

SIZE = (124, 34)


def build_corpus(home: Path) -> Path:
    """Fill a sandboxed HOME with schemes, in kitty format, and return it."""
    from cscx import emit, parse_file

    themes = home / ".config/kitty/themes"
    themes.mkdir(parents=True, exist_ok=True)

    real = Path.home() / ".config/alacritty/themes/themes"
    for stem in WANTED:
        source = real / f"{stem}.toml"
        if not source.is_file():
            continue
        palette = parse_file(source)
        palette.name = stem.replace("_", " ")
        (themes / f"{stem}.conf").write_text(emit(palette, "kitty"))

    # Always present, so the script produces something on a bare machine.
    shutil.copy(FIXTURES / "gruvbox.kitty.conf", themes / "gruvbox_dark.conf")

    count = len(list(themes.glob("*.conf")))
    print(f"corpus: {count} schemes in {themes}")
    return themes


# -- the browser ----------------------------------------------------------


async def shoot_browser(themes: Path) -> None:
    from cscx.discovery import SearchLocation
    from cscx.tui import BrowseApp

    locations = [SearchLocation("kitty themes", themes, ("*.conf",), "kitty")]

    async def app() -> BrowseApp:
        return BrowseApp(locations=locations)

    # The list, with a scheme previewed. The hero shot.
    instance = await app()
    async with instance.run_test(size=SIZE) as pilot:
        await pilot.pause()
        _select(instance, "nord")
        await pilot.pause()
        _save(instance, "browse.svg")

    # The copy dialog: every target, and where the file will go.
    instance = await app()
    async with instance.run_test(size=SIZE) as pilot:
        await pilot.pause()
        _select(instance, "nord")
        await pilot.press("c")
        await pilot.pause()
        _save(instance, "browse-copy.svg")

    # The help screen, which doubles as the feature list.
    instance = await app()
    async with instance.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        _save(instance, "browse-help.svg")


def _select(app, stem: str) -> None:
    """Highlight the scheme whose filename starts with `stem`, if present."""
    for index, found in enumerate(app._shown):
        if found.path.stem.startswith(stem):
            app.query_one("#schemes").highlighted = index
            return


def _save(app, filename: str) -> None:
    (OUT / filename).write_text(app.export_screenshot(title=f"cscx browse"))
    print(f"wrote docs/img/{filename}")


# -- the plain commands ---------------------------------------------------


def shoot_ansi(name: str, ansi: str, title: str, width: int = 100) -> None:
    """Re-render captured ANSI output as an SVG."""
    from rich.console import Console
    from rich.text import Text

    console = Console(record=True, width=width, file=open(os.devnull, "w"))
    console.print(Text.from_ansi(ansi.rstrip("\n")))
    (OUT / name).write_text(console.export_svg(title=title, clear=False))
    print(f"wrote docs/img/{name}")


def shoot_preview(themes: Path) -> None:
    from cscx import parse_file
    from cscx.preview import render

    chosen = next((p for p in sorted(themes.glob("*.conf")) if p.stem == "nord"),
                  themes / "gruvbox_dark.conf")
    shoot_ansi("preview.svg", render(parse_file(chosen)),
               f"cscx preview {chosen.name}")


def main() -> int:
    sandbox = Path(os.environ.get("CSCX_SCREENSHOT_HOME", "/tmp/cscx-screenshots"))
    shutil.rmtree(sandbox, ignore_errors=True)

    # Built while HOME is still the real one, so the schemes installed on this
    # machine can be found; everything after this point sees the sandbox, so
    # no picture carries the path of whoever generated it.
    themes = build_corpus(sandbox)
    os.environ["HOME"] = str(sandbox)

    OUT.mkdir(parents=True, exist_ok=True)
    shoot_preview(themes)
    asyncio.run(shoot_browser(themes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
