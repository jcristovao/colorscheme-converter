# Editor themes

[← README](../README.md) · [Formats](formats.md) · [Browsing](browsing.md) · [Applying](applying.md) · [Mapping](mapping.md) · [Design](design.md)

The same palette that produces a terminal theme produces an editor one.

```console
$ cscx convert ~/.config/kitty/kitty.conf --to neovim -o ~/.config/nvim/colors/mine.lua
$ cscx convert Gruvbox.colorscheme --to vim --fill
$ cscx convert Gruvbox.colorscheme --to emacs
```

| Editor | Output | Installs as |
|---|---|---|
| `vim` | `.vim` | `~/.vim/colors/NAME.vim` |
| `neovim` (`nvim`) | `.lua` | `~/.config/nvim/colors/NAME.lua` |
| `helix` (`hx`) | `.toml` | `~/.config/helix/themes/NAME.toml` |
| `emacs` | `.el` | `~/.emacs.d/themes/NAME-theme.el` |
| `vscode` (`code`) | `.json` | `~/.vscode/extensions/<ext>/themes/NAME-color-theme.json` |
| `cursor` | `.json` | `~/.cursor/extensions/<ext>/themes/…` |
| `antigravity` (`ag`) | `.json` | `~/.antigravity/extensions/<ext>/themes/…` |
| `claude-code` (`claude`, `cc`) | `.json` | `~/.claude/themes/NAME.json` |

Filenames are not free: Emacs only finds a theme named `NAME-theme.el`, and
VS Code expects `NAME-color-theme.json`, so `--to all` names them accordingly.

An editor theme needs a complete palette. Missing values that `--fill` can
derive prompt for [`--fill`](formats.md#gap-filling); a missing *hue* — one of
the eight normal ANSI colors — is refused outright, because nothing can derive
an absent hue from the others.

## Editors are written, not read

A terminal scheme is ~20 values; an editor theme is hundreds of semantic
highlight groups, so the mapping is lossy in a way that cannot be run
backwards. There is no reading a vim colorscheme back into 16 ANSI slots.

The one exception is [neovim](#reading-neovim-colorschemes-back-in), which can
be *asked* rather than parsed.

## How the mapping works

**The mapping is base16.** Something has to decide that "green" means
"string", and base16 is the established answer. Using its role names means the
group tables read the same as every base16 template in the wild: ANSI red
becomes `base08` (variables, diff deleted), blue becomes `base0D` (functions),
magenta becomes `base0E` (keywords), and so on. Every one of those choices can
be [overridden](mapping.md).

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
file says so. `--contrast RATIO` changes the target; `--contrast 0` disables
it.

**`--terminal-exact`** restricts the theme to the 16 palette colors, for exact
parity with the terminal at the cost of a flatter UI. When that costs something
real — a scheme whose `color0` equals its background has an invisible
cursorline — the generated file carries a `NOTE:` explaining it.

## Per-editor notes

**vim and neovim** emit cterm indices alongside GUI colors, so a vim in a
terminal without truecolor still looks right. A color that *is* one of the
scheme's ANSI slots emits as index 0-15, so the terminal draws it from the very
palette the theme was generated from; everything else falls back to the
256-color cube. Both also set the built-in terminal's colors, so `:terminal`
matches too.

**neovim** output covers core groups, treesitter captures, LSP semantic tokens
(linked to their treesitter equivalents, so the two cannot drift apart) and
diagnostics — 214 groups. It deliberately does not set `termguicolors`, which
is the user's setting rather than a colorscheme's business.

**helix** output names its colors in a `[palette]` table and refers to them by
role from each of 143 scopes — `"keyword" = "base0E"` rather than a repeated
hex literal — so the generated theme stays readable and editable. The
`[palette]` section is written last, because everything after a TOML table
header belongs to that table.

**emacs** output covers 89 built-in faces. Package faces — company, flycheck,
magit — are deliberately absent: they would be guesswork about what the user
has installed, and a face spec for an unloaded package is inert rather than
useful. The theme also sets `ansi-color-names-vector`, so shell and
compilation buffers use the same sixteen colors as the source terminal.

**vscode** output sets 112 workbench colors and 35 TextMate scopes, including
the integrated terminal's full sixteen — the one place a VS Code theme and a
terminal scheme agree exactly. Every workbench key emitted is one that appears
in a theme Microsoft ships with VS Code. That matters because VS Code silently
ignores keys it does not recognise: a typo would quietly do nothing rather
than fail, so "it's in a shipped theme" is the only cheap proof a key is real.
(The VS Code docs list `scrollbar.background`; no shipped theme uses it, and
the real key is `scrollbarSlider.background`.)

**cursor and antigravity** are VS Code forks that read a byte-identical theme
file — a test asserts the three outputs are identical. Only the extension
directory differs, so they are separate targets purely to document where the
file goes. Neither is installed here, so unlike VS Code their paths follow the
documented `~/.<app>/extensions` fork convention rather than being read off a
local installation.

### Packaging a VS Code theme

VS Code, Cursor and Antigravity load a theme from inside an extension rather
than on its own. `cscx activate --for vscode` generates the whole wrapper; to
build it by hand, the smallest one is a directory with the generated file
under `themes/` and a `package.json` naming it:

```json
{
  "name": "mine", "version": "1.0.0", "engines": { "vscode": "*" },
  "contributes": { "themes": [ {
    "label": "Mine", "uiTheme": "vs-dark",
    "path": "./themes/mine-color-theme.json"
  } ] }
}
```

Use `vs-light` for a light scheme. Drop the directory into
`~/.vscode/extensions`, `~/.cursor/extensions` or `~/.antigravity/extensions`
and restart.

## Claude Code

Claude Code is themable — six presets (`dark`, `light`, `dark-ansi`,
`light-ansi`, and daltonized variants) plus custom themes read from
`~/.claude/themes/<slug>.json` and selected with `"theme": "custom:<slug>"`.

**You may not need to convert anything.** `dark-ansi` and `light-ansi` render
the entire interface from the terminal's sixteen ANSI colors — so theming your
terminal themes Claude Code too, permanently, with nothing to keep in step:

```json
// ~/.claude/settings.json
{ "theme": "dark-ansi" }
```

The `claude-code` target is for the other case: dressing Claude Code in a
scheme that *isn't* your terminal's.

```console
$ cscx convert gruvbox.conf --to claude-code -o ~/.claude/themes/gruvbox.json
```

Where a scheme carries something sixteen ANSI slots can't express — its
foreground, background and selection — that value wins. `--terminal-exact`
restricts output to the ANSI slots.

### Why the token names had to be extracted, not guessed

Claude Code merges a custom theme by keeping only overrides whose token the
base preset already has and whose value is a valid color. **Everything else is
dropped with no message** — so a mistaken token name produces a theme that
loads and silently does nothing. Same trap as VS Code's `scrollbar.background`.

So the 72 tokens and their ANSI mapping are read out of the `dark-ansi` and
`light-ansi` presets in the installed binary rather than invented. Those two
differ on **37 of 72** tokens, which is why the base is chosen from the
palette's lightness instead of fixed.

A test checks the pinned list against whichever build `claude` actually runs —
and that check earned its keep immediately. It first read `2.1.76` because
version directories sort *lexically* (`2.1.76` > `2.1.221`), and that year-old
build has **67** tokens, calling one `selectionBackground` where 2.1.221 calls
it `selectionBg`. The token set really does drift between releases.

## Reading neovim colorschemes back in

Editors are written and not read here, because a colorscheme is a *program*
rather than a table of colors — parsing one is hopeless. But neovim can be
**asked**: load a colorscheme, then read back what it resolved to. That turns
out to be both easier and far more reliable than parsing would have been.

```console
$ cscx nvim-themes
cscx: wrote 178 colorschemes to ~/.cache/cscx/nvim
cscx: they now show up in `cscx browse` and `cscx list`
```

They then appear in `browse`, `list` and `convert` as a first-class source —
so you can take a neovim colorscheme and emit it as a kitty, alacritty or foot
theme. `source:neovim` in the filter narrows to just those.

**Two tiers, and each file says which it got.**

| | |
|---|---|
| `exact` | the scheme sets `terminal_color_0..15`, so the sixteen ANSI colors come from its author unchanged |
| `derived` | it doesn't, so the palette is inferred from semantic groups — `String` is green, `Function` is blue, `Keyword` is magenta |

The derived tier is the *inverse* of the base16 mapping used to write editor
themes, and it's an approximation. It's also rarely needed: **169 of 179**
colorschemes on the development machine set `terminal_color_*` outright. A
scheme too monochrome to derive a palette from is skipped rather than guessed
at.

Every scheme is loaded inside a single neovim process — one per scheme would
turn ten seconds into several minutes.

One caveat about `exact`: it means *the colors the colorscheme configures*,
which isn't always the conventional ANSI arrangement. `base16-nord` puts
`#88C0D0` (Nord's frost cyan) in `terminal_color_1`, the red slot. That looks
like a bug in the extraction and isn't — it's faithfully what neovim's
built-in `:terminal` will use.
