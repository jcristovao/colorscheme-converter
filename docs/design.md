# Design notes

[← README](../README.md) · [Formats](formats.md) · [Browsing](browsing.md) · [Applying](applying.md) · [Editors](editors.md) · [Mapping](mapping.md)

Why the thing is built the way it is. Nothing here is needed to use it.

## Hub and spoke

Every format is parsed into a single `Palette`, and every format is emitted from it. That keeps the work linear — 9 parsers plus 9 emitters — instead of the 72 directed pairs a format-to-format converter would need. Editor themes are generated from the same palette through a separate [mapping layer](editors.md#how-the-mapping-works).

## Rules the code follows

**Nothing is invented.** Every `Palette` field starts as `None` and is only set from something actually read. `palette.missing()` reports the gaps, so a caller can tell "the source omits `color3`" from "the parser dropped it". Three files in the local test corpus are genuinely incomplete; the parser says so.

**One bad line costs one color.** A theme file is not a program. An unparseable value yields `None` for that slot and parsing continues.

**Format-specific values survive in `extras`.** kitty's tab bar, konsole's opacity, alacritty's hint colors, ghostty's `background-opacity` — none have a slot in the canonical model, and all are restored when emitting back to the same format.

**Detection is scored, not guessed.** `detect_format` ranks every parser and returns confidences. The ambiguous pairs are handled explicitly: foot and alacritty both open a `[colors]` section, foot and ghostty share kebab-case `selection-*` keys, wezterm and alacritty both nest under `[colors]`.

**A format that cannot express something says so.** wezterm's `ansi` is a fixed-length array, so a source missing one normal slot gets a comment explaining the omission rather than a padded array of the wrong colors.

## Validation against the real tools

Comment syntax and key spellings were established by running the real tools, not by reading docs alone. This matters more than it sounds: X resources looks like it takes trailing `! comments`, but `xrdb -n` shows they become part of the value; and foot 1.27 rejects the `[cursor] color=` spelling that the sample config it ships still documents.

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

Helix, Emacs, ghostty, wezterm, Cursor and Antigravity are not installed here, so their output is validated structurally rather than by loading it, and the substitute is made explicit in each case:

- **Helix** — every scope name, modifier and underline style is checked against the list in the Helix theme reference, and every `[palette]` reference must resolve, since a dangling name makes Helix reject the whole theme.
- **Emacs** — the generated Elisp is parsed by a small s-expression reader in the test suite, which catches the two ways this writer could plausibly break: unbalanced parens, and an unescaped quote inside a string.
- **VS Code** — every workbench key is checked against the 138 keys extracted from the themes shipped with the locally installed VS Code, embedded in the test suite so the check runs anywhere. A second test re-extracts them from a local install when there is one, so the embedded list cannot go stale.

## Prior art

Existing tools are one-directional. base16/tinted-theming and themer generate from a palette you author in *their* format; pywal and wallust generate from a wallpaper; colortty converts *to* alacritty only. None of them read the scheme you already have.
