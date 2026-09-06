# Formats

[← README](../README.md) · [Browsing](browsing.md) · [Applying](applying.md) · [Editors](editors.md) · [Desktops](desktops.md) · [Mapping](mapping.md) · [Design](design.md)

All nine terminal formats are both read and written. The [README](../README.md#supported-formats) has the table of which files each one lives in; this page covers what converting between them actually costs.

There is a tenth format that is read but never written as a terminal scheme: KDE Plasma's `.colors`. It is written through a different route, and read back mostly so that route can be tested. → [desktop colour schemes](desktops.md)

## Color values

Values are read in every spelling these formats use: `#rgb`, `#rrggbb`, `#rrggbbaa`, `0xrrggbb`, bare `rrggbb`, X11 `rgb:rr/gg/bb`, CSS `rgb()`, decimal `r,g,b` triples, and CSS/X11 color names.

Output is written in whatever spelling the target expects, so a scheme read from X resources as `rgb:28/28/28` comes out of the kitty emitter as `#282828`.

## Identifying a file

```console
$ cscx detect ~/.config/kitty/kitty.conf
 0.95  kitty
```

Detection is scored rather than guessed, and `--from` overrides it if you already know. Extensions are documentation only — several formats share `.toml` and `.conf`, and ghostty themes have no extension at all — so the decision is made from the contents.

## What survives a conversion

Conversion is lossy in exactly one direction: toward formats with fewer concepts. A value is never silently altered, and never invented.

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

\* foot writes the cursor as `cursor=<text> <cursor>` and cannot set one half alone, so a source with only a cursor color loses it. The output says so.

**The 16 ANSI slots plus foreground and background survive every conversion.** Everything above is the trim around them.

Format-specific values that have no slot in the canonical model — kitty's tab bar, konsole's opacity, alacritty's hint colors, ghostty's `background-opacity` — are carried in `extras` and restored when emitting back to the same format.

## Gap filling

By default `cscx` emits only what it actually read, and lets the target terminal apply its own defaults. Converting from konsole, which has no cursor color, produces a kitty config with no `cursor` line.

`--fill` derives the missing values from long-standing conventions and marks each one, so a derived value is never mistaken for a stated one:

```console
$ cscx convert Gruvbox.colorscheme --to kitty --fill
cursor               #ebdbb2  # derived: foreground
cursor_text_color    #282828  # derived: background
selection_background #ebdbb2  # derived: foreground
```

The conventions:

- background and foreground fall back to `color0` and `color7`
- a missing bright slot repeats its normal counterpart
- the cursor takes the foreground, with the glyph beneath it inverted
- selection is inverse video

**Dim colors are never derived.** A dim variant is a darkened color, not a copy, and guessing one would be worse than leaving it to the terminal.

Formats without inline comments annotate on the preceding line (ghostty, X resources) or not at all (JSON, plists), in which case `cscx` reports the derived values on stderr.

## Converting everything at once

```console
$ cscx convert kitty.conf --to all -o ./out
```

Writes one file per format into `./out`, named for the scheme with each format's own extension. Editor targets are included, and their filenames follow each editor's rules — Emacs only finds a theme named `NAME-theme.el`, and VS Code expects `NAME-color-theme.json`.

## As a library

```python
from cscx import parse_file, emit, fill

palette = parse_file("~/.config/kitty/kitty.conf")
palette.missing()                    # [] when every core value was found

print(emit(palette, "ghostty"))
filled, derived = fill(palette)      # derived maps field -> where it came from
```

Every `Palette` field starts as `None` and is only set from something actually read, so `missing()` distinguishes "the source omits `color3`" from "the parser dropped it".
