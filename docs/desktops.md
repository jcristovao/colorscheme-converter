# Desktop colour schemes

[← README](../README.md) · [Formats](formats.md) · [Browsing](browsing.md) · [Applying](applying.md) · [Editors](editors.md) · [Mapping](mapping.md) · [Design](design.md)

A terminal scheme can also be written as a desktop colour scheme, so the desktop around the terminal matches the terminal. Two toolkits are supported: **KDE Plasma** and **GTK**.

```console
$ cscx convert kitty.conf --to kde -o ~/.local/share/color-schemes/Mine.colors
$ plasma-apply-colorscheme Mine
```

| Desktop | Output | Installs as |
|---|---|---|
| `kde` (`plasma`, `kde-plasma`) | `.colors` | `~/.local/share/color-schemes/NAME.colors` |
| `gtk4` (`gtk`, `gnome`, `libadwaita`, `adwaita`) | `.css` | `~/.config/gtk-4.0/gtk.css` |
| `gtk3` (`gtk-3.0`) | `.css` | `~/.config/gtk-3.0/gtk.css` |

Pair it with konsole and the whole desktop agrees:

```console
$ cscx convert kitty.conf --to kde,konsole -o ~/themes
```

## Why this works better than it looks

A `.colors` file holds eighty-four colour values — seven colour sets of twelve keys each — but it has very few real degrees of freedom, and they line up almost exactly with the base16 roles the editor layer already derives.

| KDE key | Role | |
|---|---|---|
| `ForegroundNegative` | `base08` | ANSI 1, red — errors, deletions |
| `ForegroundNeutral` | `base0A` | ANSI 3, yellow — warnings |
| `ForegroundPositive` | `base0B` | ANSI 2, green — success, additions |
| `ForegroundLink` | `base0D` | ANSI 4, blue — links |
| `ForegroundVisited` | `base0E` | ANSI 5, magenta — visited links |
| `DecorationHover` | `base0C` | ANSI 6, cyan |
| `ForegroundNormal` | `base05` | the foreground |
| `ForegroundInactive` | `base04` | placeholders, sublines, inactive titlebars |
| `View/BackgroundNormal` | `base00` | the background, verbatim |

So `cscx convert --to kde` reuses the same derivation the editor themes use, and adds one thing of its own: a **surface ramp**.

Plasma stacks its surfaces — the content view sits under the window chrome, which sits under buttons and titlebars — and the steps between them are much finer than anything an editor needs. Breeze Dark separates its view background (`20,22,24`) from its window background (`32,35,38`) by a few percent; the editor ramp's `base01` at 10% and `base02` at 22% are both too coarse and too far apart. KDE therefore gets four steps of its own, all tunable. → [tuning the mapping](mapping.md)

The direction takes care of itself. Breeze Dark sinks content *below* the chrome and Breeze Light floats it *above*, and stepping away from the background does the right thing in both cases without a special case for polarity.

## The accent

Plasma leans on a single accent colour far harder than a terminal does: focus rings, hover, active text, the selection, the titlebar tint. A terminal scheme has no such thing.

The closest candidate is the scheme's selection colour, and that is what `cscx` reaches for first — but it is tested rather than trusted. A terminal renders text *on top* of its selection, so the colour is usually chosen to sit close to the background: gruvbox's is `#504945`, barely off its own `#282828`. A focus ring in that is invisible. When the selection colour cannot carry one, the accent falls back to ANSI 4, matching base16 and Breeze's own blue.

Whichever is chosen is then moved until a focus ring drawn in it is visible on *every* surface. The hue is kept rather than swapped for a more contrasting one — a gruvbox desktop with a cyan focus ring is no longer gruvbox. The generated file records what happened:

```ini
#   accent      #579092  color4; the selection background sits too close to the
#                        chrome to carry a focus ring, moved to 3.0:1
```

Both the accent and the hover colour can be pinned to a specific ANSI slot instead. → [tuning the mapping](mapping.md)

### The hues have to move on the highlight

`Colors:Selection` needs one adjustment the other six sets do not. The accent is usually ANSI 4, and `ForegroundLink` *is* ANSI 4 — so carrying the hues across unchanged draws a link on a background of its own colour, at 1.0:1. Breeze solves this by hand, darkening its negative, neutral and positive and swapping its link to yellow outright.

`cscx` moves each hue toward whichever extreme the accent is furthest from, until it clears 2.5:1. That keeps the hue recognisable where a swap would not: gruvbox's teal link becomes a darker teal rather than becoming yellow. Only the selection set is treated this way; everywhere else the hues are written verbatim.

One limitation is worth knowing, because it looks like a bug in the generated scheme and is not. `QPalette` has a single `Link` role, taken from `Colors:View`, so a plain Qt widget drawing a link inside a *selected* row uses the view's link colour no matter what `Colors:Selection` says — only KColorScheme-aware code reads the adjusted values. The collision is upstream, and Breeze has it too:

| Scheme | View link on the highlight |
|---|---|
| Oxygen | 2.79:1 |
| Breeze Light | 1.73:1 |
| Breeze Dark | 1.22:1 |

Pulling the accent away from ANSI 4 would fix it and cost the scheme its character, so `cscx` leaves it.

`DecorationHover` is ANSI 6 rather than a copy of `DecorationFocus`. Breeze makes the two identical, but Oxygen did not, and cyan is otherwise the one hue with nowhere to go in a KDE scheme — there are five semantic foregrounds and none of them is cyan.

## What Plasma computes for itself

Several things that look missing from a `.colors` file are missing on purpose, because Plasma derives them at run time from what *is* there:

- **Bevels, frames and separators** come from `KColorScheme::shade()` applied to a set's background.
- **Disabled text** is `ForegroundNormal` faded toward the background by `[ColorEffects:Disabled]`.
- **Tinted message banners** — the error, warning and success stripes in KDE apps — are `tint(BackgroundNormal, Foreground<Role>)`. There is no `BackgroundNegative` key; writing one does nothing.
- **Hover and focus fills** are composited from `DecorationHover` and `DecorationFocus`.

That last group is why the semantic foregrounds matter more than their small screen area suggests, and the first is why the background matters more than any other single value.

### The one place a background can break Plasma

`KColorScheme::shade()` has a degenerate branch below a luminance of 0.006, where the whole Light/Midlight/Mid/Dark/Shadow family collapses onto itself. A `#000000` terminal background — common enough — therefore produces a desktop with no visible frames, bevels or separators anywhere. Breeze Dark's own view background is `20,22,24`, sitting just above that threshold, for exactly this reason.

`cscx` holds the *derived* surfaces clear of it. It does not touch the background itself, because altering a value the source actually stated is not something this program does; instead it says so:

```
cscx: the background is too dark for Plasma to shade: KColorScheme derives every
frame, bevel and separator from it, and collapses them onto one another at this
luminance. The chrome around it was held clear of that, so only frames inside
text views are affected
```

There is a matching branch at the light end, at 0.93, but it is not guarded: Breeze Light ships a pure white view background and lives in it quite happily, because when the background is light it is the dark shades that draw the frames.

## What gets checked

KDE enforces no contrast requirement of its own. An unreadable scheme installs and applies exactly like a readable one, so these warnings are the only ones anybody gets. They are printed on stderr and written into the file's header.

| Gate | Bar |
|---|---|
| Normal text against its background | 4.5:1 |
| Secondary text — placeholders, sublines, inactive titlebars | 3:1 |
| Focus rings | 3:1 |
| Disabled text, after Plasma's fade | 2:1 |
| Selected text against the highlight | 2:1 |
| Row striping distinguishable from the background | — |
| Background out of the shading range | — |

Each is reported once, naming the worst set it failed in, rather than once per colour set: the sets share their foregrounds, so a low-contrast scheme fails the same way seven times over.

The bars are calibrated against Breeze, which has to pass — a gate that fires on the scheme every KDE desktop ships with is noise, not a finding. Selected text gets its own much lower bar for that reason: Breeze Dark sits at 2.4:1 there, Breeze Light at 2.5:1, Oxygen at 2.5:1, because a saturated highlight cannot carry high-contrast text in either direction.

## Light schemes

One set has to be inverted. `Colors:Complementary` is what Plasma uses for full-screen viewers and the lock and logout screens, and both Breeze schemes make it dark regardless of their own polarity.

For a dark source it is simply the window surface. For a light source, the honest place to find a dark surface is the scheme itself: ANSI 0 is the darkest colour it states, and for a scheme with a dark counterpart — as solarized has — it is very often that counterpart's background exactly. The accent is re-derived against it, since one fitted to light surfaces would vanish on a dark one.

## Installing and applying

```console
$ cscx activate mine.conf --for kde --dry-run
$ cscx activate mine.conf --for kde
$ plasma-apply-colorscheme mine
```

`activate` writes the file where Plasma looks and stops there. Selecting it stays a deliberate act, the same way `cscx` will not edit an init file to choose an editor colorscheme — `plasma-apply-colorscheme` rewrites `kdeglobals`, which is a file you have opinions about. Once written, the scheme is validated by asking Plasma itself whether it can now see it.

To look at a generated scheme in a real application without applying anything:

```console
$ KDE_COLOR_SCHEME_PATH=$PWD/mine.colors dolphin
```

### The accent trap

If Plasma has an accent colour configured — either `AccentColor` in `kdeglobals` or "accent colour from wallpaper" — it **overrides** the scheme's `ForegroundActive`, `ForegroundLink`, `DecorationFocus`, `DecorationHover` and selection background on the way in. The scheme applies, but its accent does not. `cscx activate` checks for this and says so; clearing it is done in System Settings → Colors.

## Reading a `.colors` file back

`cscx` can parse KDE schemes, so `browse`, `list`, `detect` and `active` all see the ones installed on the machine.

It is not, however, a good way to get a terminal scheme, and the guide would rather say so than let you find out. A `.colors` file has no bright variants, no dim, no cursor, and six hues at most — and in practice not even six, because essentially every scheme in the wild copies Breeze's semantic constants verbatim:

```
                     BreezeLight        BreezeDark
ForegroundNegative   218,68,83          218,68,83     ← identical
ForegroundNeutral    246,116,0          246,116,0     ← identical
ForegroundPositive   39,174,96          39,174,96     ← identical
ForegroundVisited    155,89,182         155,89,182    ← identical
```

Converting either one gives you the same six hues. Only the values the writer puts down verbatim are read back — background, foreground and ANSI 1–6 — so ten of the sixteen slots come back unset, which is the honest answer. `ForegroundActive` and `DecorationFocus` are deliberately skipped: they hold the accent, which may be the selection colour rather than any ANSI slot, and reading them would invent a hue the source never had.

The parser earns its place another way. It is the round-trip oracle for the writer: everything else in `cscx` is checked by emitting a palette, reading it back, and asserting that nothing was lost and nothing was invented. → [contributing](contributing.md)

## Known losses

ANSI 0, 7 and 8–15 have no home in a `.colors` file, and neither do dim, the cursor, or the 256-colour indexed range. Of a full palette, KDE holds eight values.

## GTK

GTK is two targets, not one. GTK 3 and GTK 4 take colour overrides by different mechanisms, and neither file does anything for the other's applications — so `gtk4` will not theme GIMP, and `gtk3` will not theme a libadwaita application.

```console
$ cscx convert kitty.conf --to gtk3,gtk4 -o ./out
$ cscx activate kitty.conf --for gtk4
```

The bare aliases — `gtk`, `gnome`, `libadwaita` — point at **GTK 4**, since that is the modern surface. GTK 3 has to be asked for by name.

Both write colour *overrides* on top of whichever theme is in use, rather than a theme of their own. That is what makes this tractable: a real GTK theme is thousands of lines of widget CSS, while its colours are a short list.

### GTK 3

`@define-color` declarations, the mechanism Adwaita has used for a decade.

The names are the ones `libgtk-3.so` actually declares, cross-checked against the Breeze GTK 3 theme, which defines the same core set. A misspelled name is worth guarding against carefully, because it does not error: GTK parses it, stores it, and nothing ever reads it. The test suite holds the extracted list and re-extracts it from the installed library where there is one, so the copy cannot go stale.

One name people expect is missing. **GTK 3's Adwaita declares no link colour**, so `cscx` writes none rather than inventing a name that would be silently ignored.

### GTK 4 and libadwaita

CSS variables in a `:root` block, which is how libadwaita 1.9 takes overrides:

```css
:root {
  --window-bg-color: #373633;
  --view-bg-color:   #282828;
  --accent-bg-color: #579092;
}
```

libadwaita's older `@define-color` spellings still parse, but its documentation is explicit that they "are aliases of UI colors or otherwise derived from them" and "don't pick up overridden colors" — writing them would be writing something inert, so `cscx` does not.

### What is deliberately not written

Two groups, for the same reason KDE's bevels and disabled text are left alone: the toolkit computes them, and computing them better than it does is not on offer.

**Standalone colours** — `--accent-color` and its siblings, used for coloured text on a neutral background — are derived by libadwaita from the matching background colour, through an Oklab transform that clamps lightness to 0.5 on light schemes and 0.85 on dark. Overriding the background alone is the documented way to set an app-wide accent; writing the standalone colour too fights that.

**Shades, borders and outlines** — `--shade-color`, `--card-shade-color`, `--headerbar-border-color`, `--scrollbar-outline-color` — are translucent blacks and whites, sized to work over any background. A palette holds opaque colours, so putting one there replaces a working overlay with a flat slab. GTK 3's `borders` is the single exception, because Adwaita declares it as a real colour rather than an alpha.

### If you are on KDE, you may not need this

Plasma ships a GTK bridge, `kde-gtk-config`, which generates `~/.config/gtk-{3,4}.0/colors.css` from the **KDE colour scheme** and has `gtk.css` import it. Where that is installed, a scheme generated with `--to kde` already reaches GTK applications, and it does so durably.

`cscx activate --for gtk3` or `--for gtk4` detects the bridge and says so, because the bridge rewrites `gtk.css` whenever the Plasma colour scheme changes — so overrides written there are temporary:

```
note:  kde-gtk-config owns ~/.config/gtk-4.0/gtk.css and regenerates it from
       your Plasma colour scheme, so this will be overwritten the next time
       that changes; `--for kde` reaches GTK applications through that bridge
       instead, and lasts
```

The existing file is backed up first, as with any activation.

### What is not covered

**GNOME Shell.** Its theming is a full stylesheet rather than a colour list, so supporting it would mean forking and maintaining a shell theme — a different kind of artifact from everything else `cscx` writes — and it needs the User Themes extension to load at all.

**Light and dark preference.** Neither file carries one: GTK 3 reads `gtk-application-prefer-dark-theme` from `settings.ini`, and libadwaita takes it from a GSetting. `cscx` writes colours and leaves both alone.
