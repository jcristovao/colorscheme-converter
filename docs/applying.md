# Applying a scheme

[← README](../README.md) · [Formats](formats.md) · [Browsing](browsing.md) · [Editors](editors.md) · [Mapping](mapping.md) · [Design](design.md)

Three commands, in increasing order of permanence: `live` recolours the terminal you are sitting in, `activate` installs a scheme so it survives a restart, and `active` tells you what each application ended up using.

## Live preview

`cscx live FILE` recolours the running terminal immediately. No file changes, nothing to enable first, and `cscx live --reset` puts it back. In the browser, `a` applies and `u` undoes; quitting restores your colors automatically.

```console
$ cscx live ~/.config/kitty/themes/gruvbox.conf
$ cscx live --reset
```

It uses OSC escape sequences rather than any one terminal's remote-control protocol. That was the deciding factor: kitty's `@ set-colors` is excellent but needs `allow_remote_control` turned on and only works for kitty, whereas OSC works in every terminal here with nothing configured. Sequences go to `/dev/tty` rather than stdout, so they survive a pipe and don't disturb a full-screen program, and inside `tmux` they're wrapped in its passthrough form — tmux swallows them otherwise.

## Activation

`cscx activate FILE --for APP` installs a scheme so it persists. This is the only command that edits a file you didn't ask it to create, so it runs in stages you can inspect or undo:

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

`--dry-run` stops there. Otherwise the plan is printed anyway and any existing file is confirmed before being touched, unless `--yes`.

| Application | What activation does |
|---|---|
| `kitty`, `alacritty`, `foot`, `ghostty` | theme file + config edit |
| `konsole` | scheme file; `--profile` also selects it |
| `vim`, `neovim`, `helix`, `emacs` | theme file only |
| `vscode`, `cursor`, `antigravity` | the wrapping extension, generated |

### The guarantees

**Backups are never overwritten.** Existing files are copied to `NAME.cscx-TIMESTAMP.bak`, and because the timestamp is only second-resolution, a collision gets a counter — otherwise activating twice quickly would destroy the copy holding your untouched original. `--no-backup` skips this.

**Edits are idempotent.** A marker comment anchors the one line cscx owns, so activating again rewrites that line instead of appending a second include. Alacritty is the exception: its `import` has to sit inside `[general]`, and a second `[general]` would be *invalid TOML* rather than merely untidy, so that file is edited structurally.

**The application gets a veto.** Where the format can be machine-checked, the result is validated by the real thing — alacritty's TOML is re-parsed, `foot --check-config` and kitty's own loader run when installed. If the app would reject it, every backup is restored, every created file removed, and the command fails having changed nothing. `--no-validate` skips this.

**Editors never get their init file edited.** Choosing a colorscheme should stay a deliberate act, so cscx places the file and prints the one line to run (`:colorscheme gruvbox`). konsole installs the scheme but can't select it without knowing your profile, and says so rather than guessing.

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

**Terminals are read, and resolve to a file** — so the answer can be parsed and shown as colors. Getting this right needs more than a grep: kitty and foot apply directives top to bottom, so a config with both inline colors *and* an `include` has a winner that searching for `include` reports wrongly. cscx follows the ordering and says which one wins.

**Editors are asked directly.** An init file can set a colorscheme conditionally or through a plugin, and only the editor knows how that turned out — `nvim --headless -c 'lua print(vim.g.colors_name)'` is authoritative where grepping is guesswork. The answer is a *name only*: an editor theme can't be read back into 16 ANSI slots, which is the same reason editors are write-only everywhere else here. Starting vim and neovim is the slow part, so `--no-editors` skips it.

**Ambiguity is reported, not guessed.** konsole stores its scheme per profile, so several profiles give several answers — and unless `konsolerc` names a default, which one applies genuinely depends on how konsole was started.

In [`cscx browse`](browsing.md), schemes a terminal is currently using are marked in the list with a green dot.
