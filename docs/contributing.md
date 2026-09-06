# Contributing

[← README](../README.md) · [Formats](formats.md) · [Editors](editors.md) · [Desktops](desktops.md) · [Design](design.md)

```console
$ pip install -e '.[tui]'
$ python3 -m pytest
```

## Testing

The fixture set is one scheme — Gruvbox, with all 16 slots distinct so an off-by-eight in a bright/normal mapping cannot pass — written out in all ten fixture formats. Every parser must produce an identical palette from it, and every emitter must round-trip it through every parser.

The round-trip tests assert the property that matters: after emitting and re-reading, a value either survives unchanged or is absent because the target cannot hold it. Nothing is altered, and nothing appears that the source did not state.

Also swept across 167 real local files (149 alacritty themes, 17 konsole schemes, kitty.conf) converted to all 9 formats — 1503 conversions with zero crashes and zero misdetections — plus 332 editor themes generated from the same corpus, a sample of which are loaded in real neovim.

The editor tests include hostile input: a scheme name carrying a newline used to end the header comment early and turn the rest of the file into code. Names are flattened now, vim and neovim are made to load a theme built from one, and the Helix theme is checked to still parse as TOML.

The TUI is tested too, driven headlessly through Textual's pilot: filtering, moving through the list, previewing, and the whole copy-to flow including cancellation. That caught a real bug — editing the destination path and then changing the target silently discarded the edit, which is how a file lands somewhere you did not intend.

Detection is tested against crafted configs in a sandboxed `HOME`, including the ordering cases — an include that wins, and inline colors after an include that win instead. It also carries a regression test for a real bug: VS Code settings routinely contain `"file:///..."` URLs, and the naive `//` comment strip this started with truncated the line, leaving the document unparseable and the theme silently reported as unset.

Activation is tested entirely against a sandboxed `HOME`, so a wrongly built path cannot reach a real config even in a failing test. The rollback path is tested by feeding it a plan that produces invalid TOML and asserting the original comes back byte-for-byte.

The suite covers every layer: parsing, emitting, the editor mapping, colour maths, discovery, preview geometry, activation, and the TUI driven headlessly. It is not a number worth quoting here — it drifts every commit — so run `pytest -q` for the current figure.

The documentation is tested too, rather than trusted to keep up: every format, editor, command and CLI option must appear in both the man page and this documentation set, every link between these files must resolve, the man page must render without a single roff warning, and the version in `pyproject.toml`, `__version__` and the man page header must agree. That last check caught `__version__` sitting two releases behind.

## Adding a format

A format is one module in `src/cscx/formats/` (parser) and one in `src/cscx/emitters/` (emitter), each registered in its package's `_MODULES`. A test asserts the two sets stay in sync.

```python
# formats/myterm.py
NAME = "myterm"           # canonical name, used by --from and --to
ALIASES = ("mt",)         # alternate names
EXTENSIONS = (".conf",)   # documentation only; detection does not rely on it
BINARY = False            # True hands `parse` bytes instead of str

def detect(data: bytes | str, filename: str | None = None) -> float: ...
def parse(data: bytes | str, name: str | None = None) -> Palette: ...

# emitters/myterm.py
NAME = "myterm"
EXTENSION = ".conf"       # suggested extension when writing a file
BINARY = False            # True when `emit` returns bytes

def emit(palette: Palette, derived: Derivations | None = None) -> str | bytes: ...
```

Rules the existing modules follow and the tests enforce:

1. **Never invent a value.** Parsers leave a field `None` if the source did not set it; emitters omit a key rather than guessing one. Use `set_ansi` / `set_indexed`, which ignore `None` so a partial source cannot erase data.
2. **Never let one bad value abort the parse.** Wrap `parse_color` and return `None` on `ColorParseError`; every parser has a local `_safe_color`.
3. **`detect` must not raise.** It runs against files in every other format. Return `0.0` rather than throwing.
4. **Put unmappable values in `extras[NAME]`,** keyed by the format's own key names, and restore them when emitting that same format.
5. **Check the comment syntax against the real tool** before annotating output. Use `note()` for inline comments and `note_line()` for formats that have none. When in doubt, use `note_line()` — a preceding comment is valid everywhere.

Scoring guidance for `detect`: return above `0.9` only for evidence unique to your format. Shared structure — a `[colors]` section, a JSON object — is worth `0.3` or less on its own.

To add a fixture, write the Gruvbox scheme from `tests/test_parsers.py` in your format, drop it in `tests/fixtures/`, and add one line to `CASES` there and to `CAPABILITIES` in `tests/test_emitters.py`. Both suites then cover it.

## Adding an editor

Editor writers live in `src/cscx/editors/` and register in that package's `_MODULES`. A writer needs `NAME`, `EXTENSION`, `BINARY`, `INSTALL_PATH` and an `emit(palette, *, terminal_exact, contrast_target)`.

`roles.derive()` does the hard part and is fully reusable: it produces the base16 roles, the derived UI ramp and the contrast guarantee regardless of target.

The group tables, though, are per-editor, and every editor added so far has confirmed it: Helix's scopes are close to treesitter captures but not the same (`constant.character.escape`, not `@string.escape`) and it spells modifiers differently (`underlined`, `crossed_out`); Emacs uses property lists (`:weight bold`) over built-in face names; VS Code splits into a flat `colors` object and a `tokenColors` array, so its workbench half is a `WorkbenchColor` table rather than a `Group` one.

Because the colors in those tables are named by role and never by hue, the table is the only part that needs thought — rendering it is mechanical.

If the target is a fork of one already supported, don't copy the writer. `vscode_forks.py` is the pattern: delegate to the original and carry only your own `INSTALL_PATH`, with a test asserting the output stays identical.

## Adding a desktop

Desktop writers live in `src/cscx/desktops/` and follow the editors' protocol exactly — `NAME`, `EXTENSION`, `FILENAME`, `BINARY`, `INSTALL_PATH`, `emit(palette, *, terminal_exact, contrast_target)` — plus a `warnings()` of the same shape, because a desktop scheme has failure modes worth reporting that a comment in the file is not enough for.

`roles.derive()` is reused whole, the same as for an editor. What is likely to be new is a surface ramp: a desktop stacks its surfaces, and the spacing between them is a property of that desktop rather than of the palette. KDE's is four steps under `[kde]` in the mapping file, deliberately separate from `[ramp]` because Plasma's elevation is far finer than an editor's cursorline and statusline. → [desktop colour schemes](desktops.md)

Two things are worth copying from `kde.py`. Find out what the desktop *computes* rather than reads — Plasma derives every bevel, all disabled text and the tinted message banners from values in the file, so writing them is impossible and anticipating them is necessary. And calibrate any contrast gate against the scheme the desktop itself ships: a bar that the stock theme fails will fire on nearly everything and teach nobody anything. `test_breeze_passes_its_own_gates` is that check written down.

## Documentation

Every user-facing change lands in three places, and the test suite checks all three agree:

- **`docs/cscx.1`** — the reference. Every command, option, format, editor and desktop.
- **`README.md`** — the entry point. Keep it short; link out.
- **`docs/*.md`** — the detail, one page per subject.

The screenshots in `docs/img/` are generated, not captured by hand:

```console
$ python3 tools/screenshots.py
```

The browser ones come out of Textual's own `export_screenshot`, the rest are real ANSI output re-rendered by Rich, and both run against a sandboxed `HOME` holding a demo corpus — so no picture carries the path or the username of whoever generated it. Regenerate them when you change the layout of something they show.

Markdown prose is **not hard-wrapped**: one line per paragraph, and let the renderer reflow it. Wrapping at 80 columns is a habit from the man page, where it is required, and carrying it into Markdown means a two-word edit re-flows the paragraph and shows up as a six-line diff. A test enforces this.

`contrast_target` defaults to `None` in every writer so that a configured [mapping](mapping.md) is not shadowed by a module-level constant; pass values down rather than defaulting them twice.
