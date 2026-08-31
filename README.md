# cscx

Convert terminal color schemes between formats through one canonical palette.

Hub-and-spoke: every format is parsed into a single `Palette`, and every
format will be emitted from it. That keeps the work linear — N parsers plus
N emitters — instead of the N² a format-to-format converter would need.

**Status: parsers only.** Emitters are the next piece; see below.

## Why this exists

Existing tools are one-directional. base16/base24 and themer generate from a
palette you author in their own format; pywal and wallust generate from a
wallpaper; colortty converts *to* alacritty only. None of them read the scheme
you already have. This does.

## Supported formats

| Format | Files | Reads |
|---|---|---|
| `kitty` | `kitty.conf` | 256 slots, fg/bg, cursor, selection, tab bar, symbolic refs |
| `ghostty` | `config` | `palette = N=#hex`, kebab-case keys, background opacity |
| `alacritty` | `.toml`, `.yml` | both the current TOML and the pre-0.13 YAML; dim, indexed |
| `konsole` | `.colorscheme` | intense/faint variants, description, opacity |
| `iterm2` | `.itermcolors` | float components, XML and binary plists |
| `foot` | `foot.ini` | regular/bright/dim, alpha, two-value cursor, numeric slots |
| `wezterm` | `.toml` | `ansi`/`brights` arrays, `[metadata]` name |
| `windows-terminal` | `.json` | bare scheme, array, or nested in `settings.json` |
| `xresources` | `.Xresources` | `*color0:`, urxvt/xterm prefixes, `rgb:` values |

Color values are read in every spelling these formats use: `#rgb`, `#rrggbb`,
`#rrggbbaa`, `0xrrggbb`, bare `rrggbb`, X11 `rgb:rr/gg/bb`, CSS `rgb()`,
decimal `r,g,b` triples, and CSS/X11 color names.

## Usage

```console
$ cscx detect ~/.config/kitty/kitty.conf
 0.95  kitty

$ cscx parse ~/.local/share/konsole/Gruvbox.colorscheme
$ cscx parse theme.itermcolors --json
$ cscx parse weird-file --from alacritty
$ cscx formats
```

As a library:

```python
from cscx import parse_file

palette = parse_file("~/.config/kitty/kitty.conf")
palette.ansi[1].hex      # '#cc241d'
palette.missing()        # [] when every core value was found
```

## Design notes

**Nothing is invented.** Every `Palette` field starts as `None` and is only
set from something actually read. `palette.missing()` reports the gaps, so a
caller can tell "the source omits `color3`" from "the parser dropped it". Two
of the 149 alacritty themes in the wild are genuinely incomplete; the parser
says so rather than papering over it.

**One bad line costs one color.** A theme file is not a program. An
unparseable value yields `None` for that slot and parsing continues.

**Format-specific values survive in `extras`.** kitty's tab bar, konsole's
opacity, alacritty's hint colors, ghostty's `background-opacity` — none have a
slot in the canonical model, and all are kept so a round trip through cscx
does not quietly discard them.

**Detection is scored, not guessed.** `detect_format` ranks every parser and
returns confidences. The ambiguous pairs are handled explicitly: foot and
alacritty both open a `[colors]` section, foot and ghostty share kebab-case
`selection-*` keys, wezterm and alacritty both nest under `[colors]`.

## Testing

```console
$ python3 -m pytest
```

The fixture set is one scheme — Gruvbox, with all 16 slots distinct so an
off-by-eight in a bright/normal mapping cannot pass — written out in all ten
formats. Every parser must produce the identical palette from it.

Verified against 168 real files (149 alacritty themes, 17 konsole schemes,
kitty.conf, foot.ini): zero misdetections, zero parse failures.

## Next: emitters

The parse side is deliberately the harder half and it is done. Emitters are
mostly templating, and the canonical `Palette` already carries what they need.

Two things worth deciding before writing them:

1. **Gap filling.** When a source has no cursor color and the target requires
   one, the emitter must choose: omit the key, or derive it (cursor = fg is
   the usual convention). That policy belongs to the emitter, not the palette.
2. **Editors are a separate problem.** Terminal schemes are ~20 values; a
   vim/neovim scheme is hundreds of semantic highlight groups. Going to an
   editor means an opinionated 16-color → highlight-group mapping, which is
   exactly what base16 is. Treat it as its own layer rather than a tenth
   emitter, and consider borrowing tinted-theming's templates for it.

## Adding a format

Each format is one module in `src/cscx/formats/`, registered by adding it to
`_MODULES` in `formats/__init__.py`. A module must expose five names:

```python
NAME = "myterm"           # canonical name, used by --from
ALIASES = ("mt",)         # alternate names accepted by --from
EXTENSIONS = (".conf",)   # documentation only; detection does not rely on it
BINARY = False            # True hands `parse` bytes instead of str

def detect(data: bytes | str, filename: str | None = None) -> float:
    """Confidence in 0.0-1.0 that `data` is this format."""

def parse(data: bytes | str, name: str | None = None) -> Palette:
    """Read `data` into a Palette, or raise ValueError."""
```

Four rules the existing parsers follow, and the test suite enforces:

1. **Never invent a value.** Leave a field `None` if the source did not set
   it. Use `Palette.set_ansi` / `set_indexed`, which ignore `None` so a
   partial source cannot erase data already read.
2. **Never let one bad value abort the parse.** Wrap `parse_color` and return
   `None` on `ColorParseError`. Every module has a local `_safe_color` for this.
3. **`detect` must not raise.** It runs against every file, including ones in
   other formats. Return `0.0` rather than throwing; the registry catches
   exceptions, but a sniffer that throws is a bug.
4. **Put unmappable values in `extras[NAME]`,** keyed by the format's own key
   names, so nothing is silently dropped.

Scoring guidance for `detect`: return above `0.9` only for evidence unique to
your format (a distinctive key, an unmistakable filename). Shared structure —
a `[colors]` section, a JSON object — is worth `0.3` or less on its own.
Check `cscx detect` against the other fixtures after adding one; the
`test_detected_as_the_right_format` test will catch collisions.

To add a fixture, write the same Gruvbox scheme from `tests/test_parsers.py`
in your format, drop it in `tests/fixtures/`, and add one line to `CASES`
naming the optional features your format can express. The cross-format tests
then apply to it automatically.
