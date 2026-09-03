# cscx

Convert terminal color schemes between formats through one canonical palette.

Hub-and-spoke: every format is parsed into a single `Palette`, and every format
is emitted from it. That keeps the work linear — 9 parsers plus 9 emitters —
instead of the 72 directed pairs a format-to-format converter would need.
Vim, Neovim, Helix, Emacs and VS Code themes are generated from the same
palette through a separate mapping layer.

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
$ cscx browse                                     # find, preview, copy, activate
$ cscx live theme.conf                            # recolour this terminal now
$ cscx activate theme.conf --for kitty --dry-run  # see what would change

$ cscx convert ~/.local/share/konsole/Gruvbox.colorscheme --to kitty
$ cscx convert theme.itermcolors --to ghostty -o ~/.config/ghostty/config
$ cscx convert kitty.conf --to all -o ./out       # every format at once
$ cscx convert scheme.toml --to foot --fill       # derive what the source lacks

$ cscx convert kitty.conf --to neovim -o ~/.config/nvim/colors/mine.lua
$ cscx convert kitty.conf --to helix -o ~/.config/helix/themes/mine.toml
$ cscx convert kitty.conf --to emacs -o ~/.emacs.d/themes/mine-theme.el
$ cscx convert kitty.conf --to vim --terminal-exact

$ cscx detect ~/.config/kitty/kitty.conf
 0.95  kitty

$ cscx parse theme.itermcolors --json
$ cscx preview theme.itermcolors                  # colours, no browser
$ cscx list                                       # every scheme on this box
$ cscx active                                     # what each app is using now
$ cscx nvim-themes                                # read nvim's colorschemes in
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

## Browsing

`cscx browse` opens a terminal interface over the schemes you already have:
the list on the left, a preview of the highlighted one on the right, the path
it was found at along the bottom.

```
j k / ↓ ↑   move            g G          first / last
h l         list / preview  ctrl+d ctrl+u   move by ten

a   apply to this terminal now      A   activate for an application
u   undo the live preview           c   copy to another format
/   filter (fuzzy — see below)      r   rescan
?   help (also F1)                  q   quit
```

`?` or `F1` shows the keys, the filter syntax and what the list's columns mean
— the swatches, the source column, and the green dot marking a scheme a
terminal is currently using. A test asserts every binding appears there, so a
key that works but isn't documented fails the build.

Arrow keys work throughout; the vim keys work alongside them. `l` moves right
into the preview and `h` back to the list, and `j`/`k` scroll whichever pane
has focus — so `l` then `j` scrolls the preview rather than quietly moving the
selection behind it. None of them apply while the filter has focus, where they
are simply typed.

### Filtering

The browser's filter and `cscx list`'s optional query work identically.

```console
$ cscx list gruv                 # fuzzy, over name + source + format + origin
$ cscx list b16sulph             # → base16-atelier-sulphurpool
$ cscx list source:neovim gruv   # every gruvbox variant that came from neovim
$ cscx list fmt:konsole dark
```

A bare word is matched as a *subsequence*, then ranked: an exact substring
outranks a scattered match, a match starting a word outranks one mid-word, and
adjacent characters outrank spread-out ones. Several bare words must all
match, so `gruv dark` is narrower than either alone.

`source:`, `format:` and `origin:` (short: `src:`, `fmt:`) constrain a field
exactly instead. A prefix that isn't one of those is treated as ordinary text
rather than a failed constraint.

**Source is not format.** The source is the application a scheme came *from*;
the format is how it's written. They usually agree — but neovim colorschemes
are cached in kitty's format, so their source is `neovim` and their format is
`kitty`. Listings show the source, because calling them kitty would mislead.

**The preview is faithful for terminals, approximate for editors.** A terminal
scheme *is* sixteen colors plus foreground and background, so the simulated
shell session — prompt, `ls`, a dirty `git status`, a failing test, a selection
— shows exactly what the real thing will look like. The syntax sample is
painted with the base16 roles the editor writers assign, so it shows the
mapping rather than any editor's own rendering.

**Copying never touches a live config.** It writes a new file and tells you
where it went. Anything written to the default destination
(`~/.config/cscx/themes`) shows up in the list on the next rescan, because that
directory is one of the searched locations. `A` does change configuration —
see below — and shows you the plan first.

Discovery is an explicit table of theme directories rather than a walk of your
home directory: several formats have no distinctive extension — ghostty themes
have none at all — so a broad sweep would mean sniffing thousands of unrelated
files to turn up a few hundred schemes. On the development machine it finds
170 schemes in 0.07s. `--path` adds a directory or file to the search.

`browse` is the one part that needs a dependency:

```console
$ pip install 'cscx[tui]'      # Textual; everything else needs nothing
```

`cscx preview FILE` prints the same panels without the browser, and
`cscx list` prints what discovery found.

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

Where a scheme carries something sixteen ANSI slots can't express — its
foreground, background and selection — that value wins. `--terminal-exact`
restricts output to the ANSI slots.

## Neovim colorschemes, read back

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

## What is each application using?

```console
$ cscx active
kitty        ▁▁▁▁▁▁▁▁  autumn                        include in kitty.conf
alacritty    ▁▁▁▁▁▁▁▁  gruvbox_material_medium_dark  general.import
foot         ▁▁▁▁▁▁▁▁  gruvbox_material_hard_dark    last include in foot.ini
konsole      ▁▁▁▁▁▁▁▁  148925-bl1nk                  profile Alternativo
             note: konsolerc names no default profile, so which one applies
                   depends on how konsole was started
vim                    (default)                     asked vim
neovim                 gruvbox-material              asked nvim
vscode                 Kimbie Dark                   Code - OSS/User/settings.json
```

Two different questions wearing one name.

**Terminals are read, and resolve to a file** — so the answer can be parsed and
shown as colors. Getting this right needs more than a grep: kitty and foot
apply directives top to bottom, so a config with both inline colors *and* an
`include` has a winner that searching for `include` reports wrongly. cscx
follows the ordering and says which one wins.

**Editors are asked directly.** An init file can set a colorscheme
conditionally or through a plugin, and only the editor knows how that turned
out — `nvim --headless -c 'lua print(vim.g.colors_name)'` is authoritative
where grepping is guesswork. The answer is a *name only*: an editor theme
can't be read back into 16 ANSI slots, which is the same reason editors are
write-only everywhere else here. Starting vim and neovim is the slow part, so
`--no-editors` skips it.

**Ambiguity is reported, not guessed.** konsole stores its scheme per profile,
so several profiles give several answers — and unless `konsolerc` names a
default, which one applies genuinely depends on how konsole was started.

In `cscx browse`, schemes a terminal is currently using are marked in the list.

## Live preview

`cscx live FILE` recolours the running terminal immediately. No file changes,
nothing to enable first, and `cscx live --reset` puts it back. In the browser,
`a` applies and `u` undoes; quitting restores your colors automatically.

It uses OSC escape sequences rather than any one terminal's remote-control
protocol. That was the deciding factor: kitty's `@ set-colors` is excellent but
needs `allow_remote_control` turned on and only works for kitty, whereas OSC
works in every terminal here with nothing configured. Sequences go to
`/dev/tty` rather than stdout, so they survive a pipe and don't disturb a
full-screen program, and inside `tmux` they're wrapped in its passthrough form
— tmux swallows them otherwise.

## Activation

`cscx activate FILE --for APP` installs a scheme so it persists. This is the
only command that edits a file you didn't ask it to create, so it runs in
stages you can inspect or undo:

```
plan  →  back up  →  apply  →  validate  →  roll back on failure
```

```console
$ cscx activate Gruvbox.colorscheme --for kitty --dry-run
kitty:
  create  ~/.config/kitty/themes/gruvbox.conf  (the theme itself)
  edit    ~/.config/kitty/kitty.conf           (include the theme)
  reload:  kitten @ load-config, or ctrl+shift+f5 in kitty
```

`--dry-run` stops there. Otherwise the plan is printed anyway and any existing
file is confirmed before being touched, unless `--yes`.

**Backups are never overwritten.** Existing files are copied to
`NAME.cscx-TIMESTAMP.bak`, and because the timestamp is only second-resolution,
a collision gets a counter — otherwise activating twice quickly would destroy
the copy holding your untouched original.

**Edits are idempotent.** A marker comment anchors the one line cscx owns, so
activating again rewrites that line instead of appending a second include.
Alacritty is the exception: its `import` has to sit inside `[general]`, and a
second `[general]` would be *invalid TOML* rather than merely untidy, so that
file is edited structurally.

**The application gets a veto.** Where the format can be machine-checked, the
result is validated by the real thing — alacritty's TOML is re-parsed,
`foot --check-config` and kitty's own loader run when installed. If the app
would reject it, every backup is restored, every created file removed, and the
command fails having changed nothing.

| Application | What activation does |
|---|---|
| `kitty`, `alacritty`, `foot`, `ghostty` | theme file + config edit |
| `konsole` | scheme file; `--profile` also selects it |
| `vim`, `neovim`, `helix`, `emacs` | theme file only |
| `vscode`, `cursor`, `antigravity` | the wrapping extension, generated |

**Editors never get their init file edited.** Choosing a colorscheme should
stay a deliberate act, so cscx places the file and prints the one line to run
(`:colorscheme gruvbox`). konsole installs the scheme but can't select it
without knowing your profile, and says so rather than guessing.

## Editors

Editors are written, not read. A terminal scheme is ~20 values; an editor
theme is hundreds of semantic highlight groups, so the mapping is lossy in a
way that cannot be run backwards — there is no reading a vim colorscheme back
into 16 ANSI slots.

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

```console
$ cscx convert ~/.config/kitty/kitty.conf --to neovim -o ~/.config/nvim/colors/mine.lua
$ cscx convert Gruvbox.colorscheme --to vim --fill
$ cscx convert Gruvbox.colorscheme --to emacs
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

Helix output names its colors in a `[palette]` table and refers to them by
role from each of 143 scopes — `"keyword" = "base0E"` rather than a repeated
hex literal — so the generated theme stays readable and editable. The
`[palette]` section is written last, because everything after a TOML table
header belongs to that table.

Emacs output covers 89 built-in faces. Package faces — company, flycheck,
magit — are deliberately absent: they would be guesswork about what the user
has installed, and a face spec for an unloaded package is inert rather than
useful. The theme also sets `ansi-color-names-vector`, so shell and
compilation buffers use the same sixteen colors as the source terminal.

VS Code output sets 112 workbench colors and 35 TextMate scopes, including the
integrated terminal's full sixteen — the one place a VS Code theme and a
terminal scheme agree exactly. Every workbench key emitted is one that appears
in a theme Microsoft ships with VS Code. That matters because VS Code silently
ignores keys it does not recognise: a typo would quietly do nothing rather than
fail, so "it's in a shipped theme" is the only cheap proof a key is real. (The
VS Code docs list `scrollbar.background`; no shipped theme uses it, and the
real key is `scrollbarSlider.background`.)

**Cursor and Antigravity** are VS Code forks that read a byte-identical theme
file — a test asserts the three outputs are identical. Only the extension
directory differs, so they are separate targets purely to document where the
file goes. Neither is installed here, so unlike VS Code their paths follow the
documented `~/.<app>/extensions` fork convention rather than being read off a
local installation.

### Packaging a VS Code theme

VS Code, Cursor and Antigravity load a theme from inside an extension rather
than on its own. The smallest wrapper is a directory with the generated file
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
| `helix` | `tomllib`, plus scope/modifier names checked against the Helix reference |
| `emacs` | parsed with an s-expression reader: balanced forms, escaped strings |
| `vscode` family | `json`, plus every colour key checked against VS Code's own shipped themes |

Helix, Emacs, ghostty, wezterm, Cursor and Antigravity are not installed here,
so their output is validated structurally rather than by loading it, and the
substitute is made explicit in each case:

- **Helix** — every scope name, modifier and underline style is checked against
  the list in the Helix theme reference, and every `[palette]` reference must
  resolve, since a dangling name makes Helix reject the whole theme.
- **Emacs** — the generated Elisp is parsed by a small s-expression reader in
  the test suite, which catches the two ways this writer could plausibly break:
  unbalanced parens, and an unescaped quote inside a string.
- **VS Code** — every workbench key is checked against the 138 keys extracted
  from the themes shipped with the locally installed VS Code, embedded in the
  test suite so the check runs anywhere. A second test re-extracts them from a
  local install when there is one, so the embedded list cannot go stale.

## Testing

```console
$ python3 -m pytest
```

The fixture set is one scheme — Gruvbox, with all 16 slots distinct
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
are flattened now, vim and neovim are made to load a theme built from one, and
the Helix theme is checked to still parse as TOML.

The TUI is tested too, driven headlessly through Textual's pilot: filtering,
moving through the list, previewing, and the whole copy-to flow including
cancellation. That caught a real bug — editing the destination path and then
changing the target silently discarded the edit, which is how a file lands
somewhere you did not intend.

Detection is tested against crafted configs in a sandboxed `HOME`, including
the ordering cases — an include that wins, and inline colors after an include
that win instead. It also carries a regression test for a real bug: VS Code
settings routinely contain `"file:///..."` URLs, and the naive `//` comment
strip this started with truncated the line, leaving the document unparseable
and the theme silently reported as unset.

Activation is tested entirely against a sandboxed `HOME`, so a wrongly built
path cannot reach a real config even in a failing test. The rollback path is
tested by feeding it a plan that produces invalid TOML and asserting the
original comes back byte-for-byte.

The suite covers every layer: parsing, emitting, the editor mapping, colour
maths, discovery, preview geometry, activation, and the TUI driven headlessly.
It is not a number worth quoting here — it drifts every commit — so run
`pytest -q` for the current figure.

The documentation is tested too, rather than trusted to keep up: every format,
editor, command and CLI option must appear in both the man page and this file,
the man page must render without a single roff warning, and the version in
`pyproject.toml`, `__version__` and the man page header must agree. That last
check caught `__version__` sitting two releases behind.

## Documentation

```console
$ man cscx        # after install; otherwise: man -l docs/cscx.1
$ cscx formats
$ cscx convert --help
```

`docs/cscx.1` covers every command, option, format and editor, along with the
gap-filling conventions and the lossiness caveats. It installs to
`share/man/man1` on a normal `pip` or `pipx` install.

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

`roles.derive()` does the hard part and is fully reusable: it produces the
base16 roles, the derived UI ramp and the contrast guarantee regardless of
target.

The group tables, though, are per-editor, and every editor added so far has
confirmed it: Helix's scopes are close to treesitter captures but not the same
(`constant.character.escape`, not `@string.escape`) and it spells modifiers
differently (`underlined`, `crossed_out`); Emacs uses property lists
(`:weight bold`) over built-in face names; VS Code splits into a flat
`colors` object and a `tokenColors` array, so its workbench half is a
`WorkbenchColor` table rather than a `Group` one.

Because the colors in those tables are named by role and never by hue, the
table is the only part that needs thought — rendering it is mechanical.

If the target is a fork of one already supported, don't copy the writer.
`vscode_forks.py` is the pattern: delegate to the original and carry only your
own `INSTALL_PATH`, with a test asserting the output stays identical.
