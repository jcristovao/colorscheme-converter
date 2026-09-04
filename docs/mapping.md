# Tuning the mapping

[← README](../README.md) · [Formats](formats.md) · [Browsing](browsing.md) · [Applying](applying.md) · [Editors](editors.md) · [Design](design.md)

**None of this is required.** cscx works with no file present, which is the
normal case and what every generated theme has used so far. This page is for
when a default isn't to your taste.

Turning sixteen terminal colours into an [editor theme](editors.md) takes
judgement: which ANSI hue means "variable", how far the interface shades step,
how readable a comment must be. Those judgements have defaults, and
`~/.config/cscx/mapping.toml` overrides them.

```toml
[roles]
base08 = 4          # variables: blue rather than red

[ramp]
base02 = 0.35       # a heavier selection
comment_contrast = 7.0
```

```console
$ cscx mapping           # what is in effect, and where the file would be
$ cscx mapping --dump    # the same as TOML, to stdout — never written for you
$ cscx mapping --check   # validate a file
$ cscx mapping --check --path ./candidate.toml
```

## What you can change

**`[roles]`** — which ANSI slot (0-15) each base16 accent role takes.

| Role | Default | Used for |
|---|---|---|
| `base08` | `1` (red) | variables, diff deleted |
| `base09` | blended | numbers, constants |
| `base0A` | `3` (yellow) | classes, search |
| `base0B` | `2` (green) | strings, diff added |
| `base0C` | `6` (cyan) | escapes, support |
| `base0D` | `4` (blue) | functions |
| `base0E` | `5` (magenta) | keywords |
| `base0F` | blended | deprecated, embedded tags |

`base09` and `base0F` have no ANSI hue of their own and are blended by
default; naming a slot for either pins it instead. `base00` and `base05` are
the background and foreground, and `base01`-`base04`, `base06` and `base07`
are the derived ramp, so none of those is a slot anyone can reassign.

**`[ramp]`** — how far each derived UI shade steps, as a fraction of the way
from background toward foreground. `base06` and `base07` continue past the
foreground.

| Key | Default | |
|---|---|---|
| `base01` | `0.10` | statusline, cursorline |
| `base02` | `0.22` | selection |
| `base04` | `0.72` | line numbers, dark foreground |
| `base06` | `0.25` | light foreground |
| `base07` | `0.50` | lightest |
| `comment_contrast` | `4.5` | minimum WCAG ratio for comments |
| `comment_floor` | `0.45` | the window the comment search may move within |
| `comment_ceiling` | `0.85` | |

The ceiling is the one worth understanding before changing: without it, a
low-contrast scheme puts comments on top of normal text. See
[Comments are held to a contrast ratio](editors.md#how-the-mapping-works).

## Two decisions behind the design

**An overlay, not a generated default.** Writing only what you change means
everything else keeps tracking the code. A dumped copy of the defaults would
freeze at the version that produced it and silently shadow later corrections —
the same drift that has caught this project more than once. `--dump` prints to
stdout for you to copy from; it never writes. That also keeps
[`activate`](applying.md#activation) the only thing that writes into a config
directory.

**Validation is loud.** An unrecognised role or ramp key is an error naming
the alternatives, never a quietly skipped line:

```console
$ cscx mapping --check
refused: [roles] base0Z: not an accent role; expected one of base08, base09, …
```

A quietly skipped line would leave you staring at an unchanged theme with
nothing to explain it.

## What isn't exposed, and why

The tables describing another program's interface — Claude Code's token names,
VS Code's colour keys, Helix's scopes, each format's own key spellings — stay
in code. Those aren't preferences. A wrong value there doesn't produce a theme
that looks different; it produces one the application **silently ignores**,
which is a failure with nothing to see and nothing to read. That has already
happened three times in this project's history, and each time the fix was to
verify against the real thing rather than to make it easier to get wrong.
