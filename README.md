# cscx

Convert terminal color schemes between formats through one canonical palette.

Hub-and-spoke: every format is parsed into a single `Palette`, and every format
is emitted from it. That keeps the work linear — 9 parsers plus 9 emitters —
instead of the 72 directed pairs a format-to-format converter would need.
Vim and Neovim themes are generated from the same palette through a separate
mapping layer.

## Why this exists

Existing tools are one-directional. base16/tinted-theming and themer generate
from a palette you author in *their* format; pywal and wallust generate from a
wallpaper; colortty converts *to* alacritty only. None of them read the scheme
you already have. This converts between the schemes you already have.

## Supported formats

All nine are both read and written.

| Format | Files | Notes |
|---|---|---|
| `kitty` | `kitty.conf` | 256 slots, tab bar colors, symbolic refs (`cursor_text_color background`) |
| `ghostty` | `config` | `palette = N=#hex`, kebab-case keys, background opacity |
| `alacritty` | `.toml`, `.yml` | current TOML and pre-0.13 YAML; dim, indexed |
| `konsole` | `.colorscheme` | intense/faint variants, description, opacity |
| `iterm2` | `.itermcolors` | float components; reads XML and binary plists, writes XML |
| `foot` | `foot.ini` | regular/bright/dim, alpha, two-value cursor, numeric slots |
| `wezterm` | `.toml` | `ansi`/`brights` arrays, `[metadata]` name |
| `windows-terminal` | `.json` | bare scheme, array, or nested in `settings.json` |
| `xresources` | `.Xresources` | `*color0:`, urxvt/xterm prefixes, `rgb:` values |

Color values are read in every spelling these formats use: `#rgb`, `#rrggbb`,
`#rrggbbaa`, `0xrrggbb`, bare `rrggbb`, X11 `rgb:rr/gg/bb`, CSS `rgb()`,
decimal `r,g,b` triples, and CSS/X11 color names.

## Usage

```console
$ cscx convert ~/.local/share/konsole/Gruvbox.colorscheme --to kitty
$ cscx convert theme.itermcolors --to ghostty -o ~/.config/ghostty/config
$ cscx convert kitty.conf --to all -o ./out       # every format at once
$ cscx convert scheme.toml --to foot --fill       # derive what the source lacks

$ cscx convert kitty.conf --to neovim -o ~/.config/nvim/colors/mine.lua
$ cscx convert kitty.conf --to vim --terminal-exact

$ cscx detect ~/.config/kitty/kitty.conf
 0.95  kitty

$ cscx parse theme.itermcolors --json
$ cscx formats
```

As a library:

```python
from cscx import parse_file, emit, fill

palette = parse_file("~/.config/kitty/kitty.conf")
palette.missing()                    # [] when every core value was found

print(emit(palette, "ghostty"))
filled, derived = fill(palette)      # derived maps field -> where it came from
```

## What survives a conversion

Conversion is lossy in exactly one direction: toward formats with fewer
concepts. A value is never silently altered, and never invented.

| Target | cursor | under-cursor | selection bg | selection fg | dim | indexed >15 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `alacritty` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `foot` | ✓* | ✓* | ✓ | ✓ | ✓ | ✓ |
| `kitty` | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| `ghostty` | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| `wezterm` | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| `iterm2` | ✓ | ✓ | ✓ | ✓ | — | — |
| `xresources` | ✓ | — | ✓ | ✓ | — | ✓ |
| `windows-terminal` | ✓ | — | ✓ | — | — | — |
| `konsole` | — | — | — | — | ✓ | — |

\* foot writes the cursor as `cursor=<text> <cursor>` and cannot set one half
alone, so a source with only a cursor color loses it. The output says so.

The 16 ANSI slots plus foreground and background survive every conversion.

### Gap filling

By default `cscx` emits only what it actually read, and lets the target
terminal apply its own defaults. Converting from konsole, which has no cursor
color, produces a kitty config with no `cursor` line.

`--fill` derives the missing values from long-standing conventions and marks
each one, so a derived value is never mistaken for a stated one:

```console
$ cscx convert Gruvbox.colorscheme --to kitty --fill
cursor               #ebdbb2  # derived: foreground
cursor_text_color    #282828  # derived: background
selection_background #ebdbb2  # derived: foreground
```

The conventions: background and foreground fall back to `color0` and `color7`;
a missing bright slot repeats its normal counterpart; the cursor takes the
foreground with the glyph beneath it inverted; selection is inverse video.
Dim colors are never derived — a dim variant is a darkened color, not a copy,
and guessing one would be worse than leaving it to the terminal.

Formats without inline comments annotate on the preceding line (ghostty,
X resources) or not at all (JSON, plists), in which case `cscx` reports the
derived values on stderr.

## Editors

Vim and Neovim are written, not read. A terminal scheme is ~20 values; an
editor theme is hundreds of semantic highlight groups, so the mapping is lossy
in a way that cannot be run backwards — there is no reading a vim colorscheme
back into 16 ANSI slots.

```console
$ cscx convert ~/.config/kitty/kitty.conf --to neovim -o ~/.config/nvim/colors/mine.lua
$ cscx convert Gruvbox.colorscheme --to vim --fill
```

**The mapping is base16.** Something has to decide that "green" means
"string", and base16 is the established answer. Using its role names means the
group tables read the same as every base16 template in the wild: ANSI red
becomes `base08` (variables, diff deleted), blue becomes `base0D` (functions),
magenta becomes `base0E` (keywords), and so on.

**The UI shades are synthesised.** base16 has a greyscale ramp — statusline,
cursorline, line numbers, comments — that no terminal palette contains. Those
are interpolated from background toward foreground in OKLab, which matters:
linear-light blending is physically correct for compositing but visibly
overshoots, and its 8% step came out lighter than the hand-picked cursorline of
the scheme it was derived from. OKLab lands within a few points of the
hand-picked value.

**Comments are held to a contrast ratio.** An unreadable comment color is the
classic failure of a generated theme, so `base03` steps away from the
background until it clears 4.5:1 (WCAG AA). It is also *capped* at 85% of the
way to the foreground: some schemes — solarized light especially — have so
little room that hitting 4.5:1 would put comments on top of normal text,
trading one unreadable result for another. When the cap binds, the generated
file says so. `--contrast RATIO` changes the target; `--contrast 0` disables it.

**`--terminal-exact`** restricts the theme to the 16 palette colors, for exact
parity with the terminal at the cost of a flatter UI. When that costs something
real — a scheme whose `color0` equals its background has an invisible
cursorline — the generated file carries a `NOTE:` explaining it.

Both writers emit cterm indices alongside GUI colors, so a vim in a terminal
without truecolor still looks right. A color that *is* one of the scheme's ANSI
slots emits as index 0-15, so the terminal draws it from the very palette the
theme was generated from; everything else falls back to the 256-color cube.
Both also set the built-in terminal's colors, so `:terminal` matches too.

Neovim output covers core groups, treesitter captures, LSP semantic tokens
(linked to their treesitter equivalents, so the two cannot drift apart) and
diagnostics — 214 groups. It deliberately does not set `termguicolors`, which
is the user's setting rather than a colorscheme's business.

An editor theme needs a complete palette. Missing values that `--fill` can
derive prompt for `--fill`; a missing *hue* — one of the eight normal ANSI
colors — is refused outright, because nothing can derive an absent hue from
the others.

## Design notes

**Nothing is invented.** Every `Palette` field starts as `None` and is only set
from something actually read. `palette.missing()` reports the gaps, so a caller
can tell "the source omits `color3`" from "the parser dropped it". Three files
in the local test corpus are genuinely incomplete; the parser says so.

**One bad line costs one color.** A theme file is not a program. An unparseable
value yields `None` for that slot and parsing continues.

**Format-specific values survive in `extras`.** kitty's tab bar, konsole's
opacity, alacritty's hint colors, ghostty's `background-opacity` — none have a
slot in the canonical model, and all are restored when emitting back to the
same format.

**Detection is scored, not guessed.** `detect_format` ranks every parser and
returns confidences. The ambiguous pairs are handled explicitly: foot and
alacritty both open a `[colors]` section, foot and ghostty share kebab-case
`selection-*` keys, wezterm and alacritty both nest under `[colors]`.

**A format that cannot express something says so.** wezterm's `ansi` is a
fixed-length array, so a source missing one normal slot gets a comment
explaining the omission rather than a padded array of the wrong colors.

## Validation

Comment syntax and key spellings were established by running the real tools,
not by reading docs alone. This matters more than it sounds: X resources looks
like it takes trailing `! comments`, but `xrdb -n` shows they become part of
the value; and foot 1.27 rejects the `[cursor] color=` spelling that the sample
config it ships still documents.

Output is verified against each format's actual consumer where one exists:

| Format | Validated with |
|---|---|
| `kitty` | `kitty +runpy` loading it through kitty's own `load_config` |
| `foot` | `foot --check-config` |
| `alacritty` | `alacritty migrate --dry-run` |
| `xresources` | `xrdb -n` |
| `konsole` | section structure compared against a shipped scheme |
| `wezterm`, `windows-terminal`, `iterm2` | `tomllib`, `json`, `plistlib` |
| `vim` | sourced in real vim, highlights dumped and checked |
| `neovim` | sourced in real neovim, `nvim_get_hl` checked |

## Testing

```console
$ python3 -m pytest
```

613 tests. The fixture set is one scheme — Gruvbox, with all 16 slots distinct
so an off-by-eight in a bright/normal mapping cannot pass — written out in all
ten fixture formats. Every parser must produce an identical palette from it,
and every emitter must round-trip it through every parser.

The round-trip tests assert the property that matters: after emitting and
re-reading, a value either survives unchanged or is absent because the target
cannot hold it. Nothing is altered, and nothing appears that the source did not
state.

Also swept across 167 real local files (149 alacritty themes, 17 konsole
schemes, kitty.conf) converted to all 9 formats — 1503 conversions with zero
crashes and zero misdetections — plus 332 editor themes generated from the same
corpus, a sample of which are loaded in real neovim.

The editor tests include hostile input: a scheme name carrying a newline used
to end the header comment early and turn the rest of the file into code. Names
are flattened now, and both editors are made to load a theme built from one.

## Adding a format

A format is one module in `src/cscx/formats/` (parser) and one in
`src/cscx/emitters/` (emitter), each registered in its package's `_MODULES`.
A test asserts the two sets stay in sync.

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

1. **Never invent a value.** Parsers leave a field `None` if the source did not
   set it; emitters omit a key rather than guessing one. Use `set_ansi` /
   `set_indexed`, which ignore `None` so a partial source cannot erase data.
2. **Never let one bad value abort the parse.** Wrap `parse_color` and return
   `None` on `ColorParseError`; every parser has a local `_safe_color`.
3. **`detect` must not raise.** It runs against files in every other format.
   Return `0.0` rather than throwing.
4. **Put unmappable values in `extras[NAME]`,** keyed by the format's own key
   names, and restore them when emitting that same format.
5. **Check the comment syntax against the real tool** before annotating output.
   Use `note()` for inline comments and `note_line()` for formats that have
   none. When in doubt, use `note_line()` — a preceding comment is valid
   everywhere.

Scoring guidance for `detect`: return above `0.9` only for evidence unique to
your format. Shared structure — a `[colors]` section, a JSON object — is worth
`0.3` or less on its own.

To add a fixture, write the Gruvbox scheme from `tests/test_parsers.py` in your
format, drop it in `tests/fixtures/`, and add one line to `CASES` there and to
`CAPABILITIES` in `tests/test_emitters.py`. Both suites then cover it.

## Adding an editor

Editor writers live in `src/cscx/editors/` and register in that package's
`_MODULES`. A writer needs `NAME`, `EXTENSION`, `BINARY`, `INSTALL_PATH` and an
`emit(palette, *, terminal_exact, contrast_target)`.

Most of the work is already done: `roles.derive()` produces the base16 roles,
and the tables in `groups.py` are editor-agnostic — they name colors by role,
never by hue. A new writer is mostly a matter of rendering those tables in the
target's syntax. Helix (TOML), Emacs and VS Code are the obvious next ones; all
three can reuse `CORE` and most of `TREESITTER` unchanged.
