# Finding and browsing schemes

[← README](../README.md) · [Formats](formats.md) · [Applying](applying.md) · [Editors](editors.md) · [Mapping](mapping.md) · [Design](design.md)

`cscx browse` opens a terminal interface over the schemes you already have: the list on the left, a preview of the highlighted one on the right, the path it was found at along the bottom.

```console
$ pip install 'cscx[tui]'      # Textual; every other command needs nothing
$ cscx browse
```

![The browser: schemes on the left, a live preview on the right](img/browse.svg)

## Keys

```
j k / ↓ ↑   move            g G          first / last
h l         list / preview  ctrl+d ctrl+u   move by ten

a   apply to this terminal now      A   activate for an application
u   undo the live preview           c   copy to another format
/   filter (fuzzy — see below)      r   rescan
?   help (also F1)                  q   quit
```

`?` or `F1` shows the keys, the filter syntax and what the list's columns mean — the swatches, the source column, and the green dot marking a scheme a terminal is currently using. A test asserts every binding appears there, so a key that works but isn't documented fails the build.

Arrow keys work throughout; the vim keys work alongside them. `l` moves right into the preview and `h` back to the list, and `j`/`k` scroll whichever pane has focus — so `l` then `j` scrolls the preview rather than quietly moving the selection behind it. None of them apply while the filter has focus, where they are simply typed.

## Filtering

The browser's filter and `cscx list`'s optional query work identically.

```console
$ cscx list gruv                 # fuzzy, over name + source + format + origin
$ cscx list b16sulph             # → base16-atelier-sulphurpool
$ cscx list source:neovim gruv   # every gruvbox variant that came from neovim
$ cscx list fmt:konsole dark
```

A bare word is matched as a *subsequence*, then ranked: an exact substring outranks a scattered match, a match starting a word outranks one mid-word, and adjacent characters outrank spread-out ones. Several bare words must all match, so `gruv dark` is narrower than either alone.

`source:`, `format:` and `origin:` (short: `src:`, `fmt:`) constrain a field exactly instead. A prefix that isn't one of those is treated as ordinary text rather than a failed constraint.

### Source is not format

The source is the application a scheme came *from*; the format is how it's written. They usually agree — but [neovim colorschemes](editors.md#reading-neovim-colorschemes-back-in) are cached in kitty's format, so their source is `neovim` and their format is `kitty`. Listings show the source, because calling them kitty would mislead.

## What the preview shows

**Faithful for terminals, approximate for editors.** A terminal scheme *is* sixteen colors plus foreground and background, so the simulated shell session — prompt, `ls`, a dirty `git status`, a failing test, a selection — shows exactly what the real thing will look like.

The syntax sample is painted with the [base16 roles](editors.md#how-the-mapping-works) the editor writers assign, so it shows the mapping rather than any editor's own rendering.

`cscx preview FILE` prints the same panels without the browser.

![cscx preview, printing the same panels to the terminal](img/preview.svg)

## Copying a scheme

`c` in the browser writes the highlighted scheme out in another format.

![The copy dialog, with its seventeen targets and the destination for each](img/browse-copy.svg)

**Copying never touches a live config.** It writes a new file and tells you where it went — into the directory that application reads themes from (`~/.claude/themes` for Claude Code, `~/.config/nvim/colors` for neovim), since a theme written where the program never looks does nothing at all. Type to narrow the seventeen targets.

Only the theme is written; pointing the application at it is what `A` does — see [Applying a scheme](applying.md). Anything written to the default destination (`~/.config/cscx/themes`) shows up in the list on the next rescan, because that directory is one of the searched locations.

## Where schemes are found

Discovery is an explicit table of theme directories rather than a walk of your home directory: several formats have no distinctive extension — ghostty themes have none at all — so a broad sweep would mean sniffing thousands of unrelated files to turn up a few hundred schemes. On the development machine it finds 170 schemes in 0.07s.

`--path` adds a directory or file to the search, which is what pointing at a downloaded theme pack should mean:

```console
$ cscx browse --path ~/Downloads/base16-kitty
$ cscx list --path ~/Downloads/base16-kitty
```
