# cscx

Convert terminal color schemes between formats — and into editor themes —
through one canonical palette.

You already have the scheme you want. It's in kitty's config, or a konsole
`.colorscheme`, or a neovim colorscheme you've used for years. `cscx` reads it
and writes it out anywhere else: nine terminal formats, eight editors, in any
direction.

```console
$ cscx browse                                          # find, preview, apply
$ cscx convert Gruvbox.colorscheme --to kitty          # one file, another format
$ cscx convert kitty.conf --to all -o ./out            # every format at once
```

Existing tools go one way only: base16 and themer generate from a palette you
author in *their* format, pywal generates from a wallpaper, colortty converts
*to* alacritty. None of them read the scheme you already have.

## Install

```console
$ pipx install '.[tui]'        # from a clone; --editable to track your changes
$ pip install '.[tui]'         # or into the current environment
```

Python 3.11+. The converter itself has **no dependencies** — the `[tui]` extra
is only for `cscx browse`, and `pipx install .` without it gives you every
other command. Installing also puts `man cscx` in place.

## Try it

```console
$ cscx list                  # every scheme already on this machine
$ cscx browse                # pick one, see it, press `a` to try it live
```

`browse` is the fastest way in: the schemes you have on the left, a live
preview on the right, and single keys to try one in this terminal (`a`), copy
it to another format (`c`) or install it for an application (`A`).

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

The 16 ANSI slots plus foreground and background survive every conversion; the
trim around them (cursor, selection, dim, indexed) depends on the target.
→ [what survives a conversion](docs/formats.md#what-survives-a-conversion)

## Editors

The same palette also produces a full editor theme.

| Editor | Output | Installs as |
|---|---|---|
| `vim` | `.vim` | `~/.vim/colors/NAME.vim` |
| `neovim` (`nvim`) | `.lua` | `~/.config/nvim/colors/NAME.lua` |
| `helix` (`hx`) | `.toml` | `~/.config/helix/themes/NAME.toml` |
| `emacs` | `.el` | `~/.emacs.d/themes/NAME-theme.el` |
| `vscode` (`code`) | `.json` | inside an extension |
| `cursor` | `.json` | inside an extension |
| `antigravity` (`ag`) | `.json` | inside an extension |
| `claude-code` (`claude`, `cc`) | `.json` | `~/.claude/themes/NAME.json` |

```console
$ cscx convert kitty.conf --to neovim -o ~/.config/nvim/colors/mine.lua
```

Editors are written, not read — with one exception: neovim colorschemes can be
read *back* into palettes, so a theme you love in your editor can become your
terminal's. → [editor themes](docs/editors.md)

## Commands

| | |
|---|---|
| [`cscx browse`](docs/browsing.md) | find, preview, copy and install schemes |
| [`cscx list`](docs/browsing.md#filtering) | every scheme on this machine, filterable |
| [`cscx preview`](docs/browsing.md#what-the-preview-shows) | show one scheme's colors, no browser |
| [`cscx convert`](docs/formats.md) | one scheme, another format |
| [`cscx detect`](docs/formats.md#identifying-a-file) | what format is this file? |
| [`cscx parse`](docs/formats.md#as-a-library) | dump a scheme as JSON |
| [`cscx live`](docs/applying.md#live-preview) | recolour this terminal now, `--reset` to undo |
| [`cscx activate`](docs/applying.md#activation) | install a scheme so it persists |
| [`cscx active`](docs/applying.md#what-is-each-application-using) | what is each application using? |
| [`cscx nvim-themes`](docs/editors.md#reading-neovim-colorschemes-back-in) | read neovim's colorschemes in as sources |
| [`cscx mapping`](docs/mapping.md) | inspect or check the editor mapping |
| `cscx formats` | list every format, editor and alias |

Every command takes `--help`, and `man cscx` is the full reference.

## Three things worth knowing

**Nothing is invented.** By default `cscx` emits only what it actually read.
Converting from konsole, which has no cursor color, produces a kitty config
with no `cursor` line — the terminal applies its own default. `--fill` derives
the missing values from long-standing conventions and marks each one, so a
derived value is never mistaken for a stated one.
→ [gap filling](docs/formats.md#gap-filling)

**Only `activate` changes your configuration.** `convert` and the browser's
copy write new files and tell you where they went. `activate` is the one
command that edits a file you didn't ask it to create, and it plans, backs up,
validates with the real application, and rolls back if that application would
reject the result. → [applying a scheme](docs/applying.md)

**The editor mapping is yours to change.** Which ANSI hue means "variable",
how far the interface shades step, how readable a comment must be — all have
defaults that need no configuration, and all can be overridden in
`~/.config/cscx/mapping.toml`. → [tuning the mapping](docs/mapping.md)

## Documentation

```console
$ man cscx        # after install; otherwise: man -l docs/cscx.1
$ cscx formats
$ cscx convert --help
```

`docs/cscx.1` is the reference: every command, option, format and editor.
These pages are the detail behind it:

- [Formats](docs/formats.md) — color spellings, what survives a conversion, gap filling
- [Finding and browsing](docs/browsing.md) — the browser, fuzzy filtering, where schemes are found
- [Applying a scheme](docs/applying.md) — live preview, activation, what each app is using
- [Editor themes](docs/editors.md) — the base16 mapping, per-editor notes, Claude Code, neovim read-back
- [Tuning the mapping](docs/mapping.md) — the optional `mapping.toml`
- [Design notes](docs/design.md) — why it's built this way, and how each format was verified
- [Contributing](docs/contributing.md) — testing, adding a format, adding an editor

## License

MIT.
