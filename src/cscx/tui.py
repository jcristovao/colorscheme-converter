"""A terminal browser for every scheme on the machine.

Three things, matching what the converter can honestly do today: find the
schemes you already have, show what each one looks like, and write one out in
another format. It does not touch a live config -- copying writes a new file
and tells you where it went.

Textual is an optional dependency; `cscx browse` says so rather than failing
with an import error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from . import __version__, live
from .active import detect as detect_active
from .activation import ACTIVATABLE, ActivationError, apply_plan, plan
from .fuzzy import rank
from .discovery import (
    Discovered,
    SearchLocation,
    discover,
    filter_schemes,
    installed_applications,
)
from .editors import EDITORS, EditorPaletteError, get_editor
from .emitters import EMITTERS, get_emitter
from .formats import parse_file
from .palette import Palette
from .preview import render, swatch_strip

__all__ = ["BrowseApp", "run"]

#: Where a copied theme goes by default. Discovery scans this directory, so
#: anything written here shows up in the list on the next rescan.
DEFAULT_OUTPUT = Path("~/.config/cscx/themes")

#: How far ctrl+d and ctrl+u move through the list.
_PAGE = 10

#: The help screen, as (section, [(keys, what it does)]). A test asserts every
#: binding with a description appears here, so the two cannot drift apart.
HELP: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Moving", (
        ("j / k  or  down / up", "move through the list"),
        ("g / G", "first / last entry"),
        ("ctrl+d / ctrl+u", "move by ten"),
        ("l / h", "into the preview / back to the list"),
        ("", "j and k scroll whichever pane has focus"),
    )),
    ("Finding", (
        ("/", "focus the filter"),
        ("", "a bare word matches name, source, format and origin, fuzzily"),
        ("", "several words must all match:  gruv dark"),
        ("", "source:neovim  format:kitty  origin:...  narrow one field"),
        ("", "src: and fmt: are accepted short forms"),
        ("escape", "leave the filter, back to the list"),
    )),
    ("Doing", (
        ("c", "copy the scheme to another format, into a file"),
        ("", "type to narrow the targets; it defaults to where that app looks"),
        ("a", "apply it to this terminal now (nothing is written)"),
        ("u", "undo that; quitting undoes it too"),
        ("A", "activate it for an application, editing its config"),
        ("", "the plan is shown first, and existing files are backed up"),
        ("r", "rescan for schemes"),
    )),
    ("Reading the list", (
        ("", "the swatches are the scheme's own sixteen ANSI colours"),
        ("", "the second column is the source: which application it came from"),
        ("", "a green dot marks a scheme a terminal is currently using"),
    )),
    ("Elsewhere", (
        ("?  or  F1", "this help"),
        ("q", "quit"),
        ("", "man cscx covers the command line"),
    )),
)


@dataclass(frozen=True, slots=True)
class Target:
    """Something a scheme can be written as."""

    name: str
    kind: str          # "terminal" or "editor"
    filename: str      # template with {name}

    @property
    def label(self) -> str:
        return f"{self.name}  ({self.kind})"


def _targets() -> list[Target]:
    targets = [
        Target(name, "terminal", f"{{name}}.{name}{get_emitter(name).EXTENSION}")
        for name in sorted(EMITTERS)
    ]
    targets += [
        Target(name, "editor", get_editor(name).FILENAME) for name in sorted(EDITORS)
    ]
    return targets


def destination_for(palette: Palette, target: Target, scheme_name: str) -> Path:
    """Where a copy of `palette` should go for `target`.

    The directory the application actually reads themes from, not a scratch
    directory of our own: a theme written somewhere the program never looks is
    a theme that silently does nothing. Applications cscx cannot place a theme
    for -- iTerm2, wezterm, Windows Terminal, X resources have no single
    conventional location -- fall back to `~/.config/cscx/themes`, which is one
    of the directories `browse` itself scans.

    Copying still writes only the theme. Pointing the application at it is what
    `activate` does.
    """
    stem = _slugify(scheme_name)
    try:
        if (path := plan(palette, target.name, name=stem).theme_path) is not None:
            return path
    except (ActivationError, KeyError):
        pass
    return DEFAULT_OUTPUT.expanduser() / target.filename.format(name=stem)


class CopyToScreen(ModalScreen[tuple[Target, Path] | None]):
    """Pick a target format and confirm where the file goes."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Cancel"),
        # The filter holds focus, so the list is driven from here.
        Binding("down", "move(1)", "Next", show=False),
        Binding("up", "move(-1)", "Previous", show=False),
    ]

    def __init__(self, palette: Palette, scheme_name: str) -> None:
        super().__init__()
        self._palette = palette
        self._scheme_name = scheme_name
        self._targets = _targets()
        self._shown: list[Target] = list(self._targets)
        #: The last path this screen filled in itself. Used to tell an
        #: untouched suggestion from one the user has edited.
        self._suggested = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="copy-dialog"):
            yield Label(f"Copy “{self._scheme_name}” to:", id="copy-title")
            yield Input(
                placeholder=f"type to narrow {len(self._targets)} targets…",
                id="copy-filter",
            )
            yield OptionList(id="copy-targets")
            yield Label("Destination", classes="dim")
            yield Input(id="copy-path")
            yield Label("up/down choose · enter writes it · esc cancels",
                        classes="dim")

    def on_mount(self) -> None:
        self._refill("")
        # Focus the filter, not the list: a short terminal cannot show all
        # seventeen targets, and typing two letters beats scrolling for one
        # that happens to be off-screen.
        self.query_one("#copy-filter", Input).focus()

    def _refill(self, needle: str) -> None:
        self._shown = rank(needle.strip(), self._targets, key=lambda t: t.label)
        options = self.query_one("#copy-targets", OptionList)
        options.clear_options()
        options.add_options([Option(t.label, id=t.name) for t in self._shown])
        if self._shown:
            options.highlighted = 0

    def _sync_path(self, target: Target) -> None:
        """Suggest a path for `target`, without discarding a typed one.

        Changing the target re-suggests only while the field still holds the
        previous suggestion. Once it has been edited, the edit wins -- silently
        reverting someone's typing is how a file lands somewhere unintended.
        """
        field = self.query_one("#copy-path", Input)
        if field.value and field.value != self._suggested:
            return
        self._suggested = str(destination_for(self._palette, target, self._scheme_name))
        field.value = self._suggested

    @on(Input.Changed, "#copy-filter")
    def _filter_changed(self, event: Input.Changed) -> None:
        self._refill(event.value)

    @on(OptionList.OptionHighlighted, "#copy-targets")
    def _highlight(self, event: OptionList.OptionHighlighted) -> None:
        if self._shown:
            self._sync_path(self._shown[event.option_index])

    @on(OptionList.OptionSelected, "#copy-targets")
    def _select(self, event: OptionList.OptionSelected) -> None:
        self._confirm(self._shown[event.option_index])

    @on(Input.Submitted)
    def _submitted(self) -> None:
        if (target := self.highlighted()) is not None:
            self._confirm(target)

    def highlighted(self) -> Target | None:
        index = self.query_one("#copy-targets", OptionList).highlighted
        if index is None or not self._shown:
            return None
        return self._shown[index]

    def _confirm(self, target: Target) -> None:
        self.dismiss((target, Path(self.query_one("#copy-path", Input).value)))

    def action_move(self, delta: int) -> None:
        options = self.query_one("#copy-targets", OptionList)
        if not self._shown:
            return
        current = options.highlighted or 0
        options.highlighted = max(0, min(len(self._shown) - 1, current + delta))

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class ActivateScreen(ModalScreen[str | None]):
    """Choose an application, see exactly what would change, then confirm."""

    BINDINGS = [Binding("escape", "dismiss_screen", "Cancel")]

    def __init__(self, palette: Palette, installed: set[str]) -> None:
        super().__init__()
        self._palette = palette
        # Applications actually present come first: activating for something
        # that is not installed is legal but rarely what anyone means.
        self._apps = sorted(ACTIVATABLE, key=lambda a: (a not in installed, a))
        self._installed = installed

    def compose(self) -> ComposeResult:
        with Vertical(id="activate-dialog"):
            yield Label("Activate for:", id="activate-title")
            yield OptionList(
                *(
                    Option(f"{app}{'' if app in self._installed else '   (not installed)'}",
                           id=app)
                    for app in self._apps
                ),
                id="activate-apps",
            )
            yield Static("", id="activate-plan")
            yield Label("enter applies · esc cancels", classes="dim")

    def on_mount(self) -> None:
        self.query_one("#activate-apps", OptionList).focus()
        self._show_plan(self._apps[0])

    def _show_plan(self, app: str) -> None:
        try:
            described = plan(self._palette, app).describe()
        except ActivationError as exc:
            described = str(exc)
        self.query_one("#activate-plan", Static).update(described)

    @on(OptionList.OptionHighlighted, "#activate-apps")
    def _highlight(self, event: OptionList.OptionHighlighted) -> None:
        self._show_plan(self._apps[event.option_index])

    @on(OptionList.OptionSelected, "#activate-apps")
    def _select(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._apps[event.option_index])

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """The keys, and the things about the list that are not self-evident."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Close"),
        Binding("question_mark", "dismiss_screen", "Close", show=False),
        Binding("f1", "dismiss_screen", "Close", show=False),
        Binding("q", "dismiss_screen", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-dialog"):
            yield Label("cscx — browsing schemes", id="help-title")
            for section, rows in HELP:
                yield Label(section, classes="help-section")
                for keys, description in rows:
                    yield Label(self._row(keys, description), classes="help-row")
            yield Label("any of  esc  ?  F1  q  closes this", classes="dim")

    @staticmethod
    def _row(keys: str, description: str) -> Text:
        row = Text()
        row.append(f"  {keys:<22}", style="bold" if keys else "")
        row.append(description, style="" if keys else "italic dim")
        return row

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class BrowseApp(App[None]):
    """Browse, preview and copy the schemes on this machine."""

    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #sidebar { width: 42; border-right: solid $panel; }
    #filter { border: none; }
    #schemes { height: 1fr; }
    #preview-pane { padding: 0 1; }
    #status { height: 1; color: $text-muted; padding: 0 1; }
    .dim { color: $text-muted; }
    #copy-dialog {
        width: 70; height: 90%; padding: 1 2;
        background: $surface; border: thick $primary;
    }
    /* 1fr, not a fixed height: seventeen targets in a twelve-row box hid a
       third of them with nothing to say so. */
    #copy-targets { height: 1fr; }
    #activate-dialog {
        width: 88; max-height: 90%; padding: 1 2;
        background: $surface; border: thick $warning;
    }
    #activate-apps { height: 14; }
    #activate-plan { height: auto; padding: 1 0 0 0; color: $text-muted; }
    #help-dialog {
        width: 74; max-height: 90%; padding: 1 2;
        background: $surface; border: thick $primary;
    }
    #help-title { text-style: bold; padding-bottom: 1; }
    .help-section { color: $accent; text-style: bold; padding-top: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        Binding("f1", "help", "Help", show=False),
        Binding("slash", "focus_filter", "Filter"),
        Binding("c", "copy_to", "Copy to"),
        Binding("a", "live_apply", "Live"),
        Binding("u", "live_reset", "Undo live"),
        Binding("A", "activate", "Activate"),
        Binding("r", "rescan", "Rescan"),
        Binding("escape", "focus_list", "Back to list", show=False),

        # vim navigation alongside the arrow keys. These only reach the app
        # when the filter does not have focus, since an Input consumes
        # printable keys -- so typing "j" into the filter still types a "j".
        Binding("j", "nav_down", "Down", show=False),
        Binding("k", "nav_up", "Up", show=False),
        Binding("l", "focus_preview", "Preview pane", show=False),
        Binding("h", "focus_list", "List pane", show=False),
        Binding("g", "nav_first", "Top", show=False),
        Binding("G", "nav_last", "Bottom", show=False),
        Binding("ctrl+d", "nav_page_down", "Half page down", show=False),
        Binding("ctrl+u", "nav_page_up", "Half page up", show=False),
    ]

    def __init__(
        self,
        extra: list[Path] | None = None,
        *,
        locations: list[SearchLocation] | None = None,
    ) -> None:
        super().__init__()
        self._extra = extra or []
        #: Overrides the default search table. Tests pin this so the app does
        #: not depend on what happens to be installed.
        self._locations = locations
        self._all: list[Discovered] = []
        self._shown: list[Discovered] = []
        self._cache: dict[Path, Palette] = {}
        #: The plain text of the current preview. Kept so tests (and anything
        #: else) can read it without reaching into Textual's widget internals.
        self.preview_text: str = ""
        #: Destinations written this session, most recent last.
        self.written: list[Path] = []
        #: Set while the terminal is showing a scheme that is not its own.
        self.live_scheme: str | None = None
        #: Applications activated this session, for tests and for the log.
        self.activated: list[str] = []
        #: Resolved path -> the applications currently using it.
        self.in_use: dict[Path, list[str]] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Input(placeholder="filter — try  gruv  or  source:neovim", id="filter")
                yield OptionList(id="schemes")
            with VerticalScroll(id="preview-pane"):
                yield Static("", id="preview")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"cscx {__version__}"
        self.action_rescan()
        # The preview has to be focusable for `l` to move into it.
        self.query_one("#preview-pane", VerticalScroll).can_focus = True
        # The list takes focus, not the filter: single-key bindings like `c`
        # and `j` would otherwise be typed into the filter field instead.
        self.query_one("#schemes", OptionList).focus()

    # -- data ------------------------------------------------------------

    def action_rescan(self) -> None:
        self._all = discover(self._extra, locations=self._locations)
        self._cache.clear()
        self._refresh_in_use()
        self._apply_filter(self.query_one("#filter", Input).value)
        sources = len({found.source for found in self._all})
        self.sub_title = f"{len(self._all)} schemes from {sources} sources"

    def _refresh_in_use(self) -> None:
        """Which discovered scheme each terminal is currently using.

        Editors are skipped: asking them means starting vim and neovim, and
        they answer with a name rather than a file, so there is nothing here
        to match a discovered path against.
        """
        self.in_use = {}
        try:
            for entry in detect_active(editors=False):
                if entry.path is not None:
                    self.in_use.setdefault(entry.path.resolve(), []).append(entry.app)
        except Exception:
            self.in_use = {}

    def _apply_filter(self, needle: str) -> None:
        # filter_schemes returns best-first, so the order it gives is kept.
        self._shown = filter_schemes(needle.strip(), self._all)

        options = self.query_one("#schemes", OptionList)
        options.clear_options()
        options.add_options([Option(self._row(d)) for d in self._shown])
        if self._shown:
            options.highlighted = 0
        else:
            self._set_preview(Text("no scheme matches that filter"))

    def _row(self, found: Discovered) -> Text:
        """A list row: sixteen swatches, then the name and format."""
        try:
            row = Text.from_ansi(swatch_strip(self._palette(found.path), width=1))
        except Exception:
            # One unreadable file must cost one row, not the whole list.
            row = Text(" " * 16, style="dim")
        row.append(f" {found.name}", style="bold")
        # The source, not the format: neovim schemes are cached as kitty
        # files, and labelling them "kitty" here would be misleading.
        row.append(f"  {found.source}", style="dim")
        if users := self.in_use.get(found.path):
            row.append(f"  ● in use by {', '.join(users)}", style="bold green")
        return row

    def _palette(self, path: Path) -> Palette:
        if path not in self._cache:
            self._cache[path] = parse_file(path)
        return self._cache[path]

    # -- preview ---------------------------------------------------------

    @on(OptionList.OptionHighlighted, "#schemes")
    def _preview_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if not self._shown:
            return
        found = self._shown[event.option_index]
        try:
            palette = self._palette(found.path)
        except Exception as exc:                      # a bad file must not kill the app
            self._set_preview(Text(f"could not read {found.path}: {exc}"))
            return
        self._set_preview(Text.from_ansi(render(palette)))
        self.query_one("#status", Static).update(
            f"{found.path}  ·  {found.format} {found.confidence:.2f}  ·  {found.origin}"
            + (f"  ·  {len(self._shown)}/{len(self._all)} shown"
               if len(self._shown) != len(self._all) else "")
        )

    def _set_preview(self, renderable: Text) -> None:
        self.preview_text = renderable.plain
        self.query_one("#preview", Static).update(renderable)

    # -- actions ---------------------------------------------------------

    @on(Input.Changed, "#filter")
    def _filter_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    @on(Input.Submitted, "#filter")
    def _filter_submitted(self) -> None:
        self.query_one("#schemes", OptionList).focus()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_focus_list(self) -> None:
        self.query_one("#schemes", OptionList).focus()

    def action_focus_preview(self) -> None:
        """`l` moves right, into the preview, where j/k then scroll it."""
        self.query_one("#preview-pane", VerticalScroll).focus()

    # -- vim-style navigation ---------------------------------------------
    #
    # j and k mean "down" and "up" in whichever pane has focus, which is what
    # makes `l j j` scroll the preview rather than quietly moving the list
    # behind it.

    def _preview_pane(self) -> VerticalScroll | None:
        pane = self.query_one("#preview-pane", VerticalScroll)
        return pane if self.focused is pane else None

    def _move(self, delta: int) -> None:
        options = self.query_one("#schemes", OptionList)
        if not self._shown:
            return
        current = options.highlighted or 0
        options.highlighted = max(0, min(len(self._shown) - 1, current + delta))

    def action_nav_down(self) -> None:
        if (pane := self._preview_pane()) is not None:
            pane.scroll_down()
            return
        self._move(1)

    def action_nav_up(self) -> None:
        if (pane := self._preview_pane()) is not None:
            pane.scroll_up()
            return
        self._move(-1)

    def action_nav_first(self) -> None:
        if (pane := self._preview_pane()) is not None:
            pane.scroll_home()
            return
        self._move(-len(self._shown))

    def action_nav_last(self) -> None:
        if (pane := self._preview_pane()) is not None:
            pane.scroll_end()
            return
        self._move(len(self._shown))

    def action_nav_page_down(self) -> None:
        if (pane := self._preview_pane()) is not None:
            pane.scroll_page_down()
            return
        self._move(_PAGE)

    def action_nav_page_up(self) -> None:
        if (pane := self._preview_pane()) is not None:
            pane.scroll_page_up()
            return
        self._move(-_PAGE)

    def action_copy_to(self) -> None:
        if not (found := self.current()):
            return
        try:
            palette = self._palette(found.path)
        except Exception as exc:
            self.notify(str(exc), title="could not read", severity="error")
            return

        # Name the file after the scheme's own name where it has one -- konsole
        # records a Description, for instance -- so the filename and the name
        # written inside the file agree.
        self.push_screen(
            CopyToScreen(palette, palette.name or found.name), self._write_copy
        )

    def action_live_apply(self) -> None:
        """Recolour the real terminal, so the scheme can be judged in use."""
        if not (found := self.current()):
            return
        try:
            palette = self._palette(found.path)
        except Exception as exc:
            self.notify(str(exc), title="could not read", severity="error")
            return

        if not live.is_supported() or not live.apply(palette):
            self.notify("no terminal here to recolour", severity="warning")
            return
        self.live_scheme = found.name
        self.notify(f"{found.name} — press u to restore", title="applied live")

    def action_live_reset(self) -> None:
        if self.live_scheme is None:
            return
        live.reset()
        self.live_scheme = None
        self.notify("terminal colours restored")

    def action_activate(self) -> None:
        if not (found := self.current()):
            return
        try:
            palette = self._palette(found.path)
        except Exception as exc:
            self.notify(str(exc), title="could not read", severity="error")
            return
        self.push_screen(
            ActivateScreen(palette, installed_applications()),
            lambda app: self._activate(app, palette),
        )

    def _activate(self, app: str | None, palette: Palette) -> None:
        if app is None:
            return
        try:
            proposed = plan(palette, app)
            backups = apply_plan(proposed)
        except (ActivationError, OSError) as exc:
            self.notify(str(exc), title=f"{app} unchanged", severity="error")
            return

        self.activated.append(app)
        detail = proposed.reload or "done"
        if backups:
            detail += f"  ·  backed up {len(backups)} file(s)"
        self.notify(detail, title=f"activated for {app}")

    def on_unmount(self) -> None:
        """Never leave the terminal wearing a scheme the user only previewed."""
        if self.live_scheme is not None:
            live.reset()
            self.live_scheme = None

    def current(self) -> Discovered | None:
        options = self.query_one("#schemes", OptionList)
        index = options.highlighted
        if index is None or not self._shown:
            return None
        return self._shown[index]

    def _write_copy(self, result: tuple[Target, Path] | None) -> None:
        if result is None:
            return
        target, destination = result
        found = self.current()
        if found is None:
            return

        try:
            palette = self._palette(found.path)
            rendered = _render_target(palette, target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(rendered, bytes):
                destination.write_bytes(rendered)
            else:
                destination.write_text(rendered)
        except EditorPaletteError as exc:
            self.notify(str(exc), title=f"{target.name} needs more", severity="warning")
            return
        except OSError as exc:
            self.notify(str(exc), title="could not write", severity="error")
            return

        self.written.append(destination)
        self.notify(str(destination), title=f"wrote {target.name}")


def _render_target(palette: Palette, target: Target) -> str | bytes:
    if target.kind == "editor":
        return get_editor(target.name).emit(palette)
    return get_emitter(target.name).emit(palette, None)


def _slugify(name: str) -> str:
    from .editors._common import slug

    return slug(name)


def run(extra: list[Path] | None = None) -> int:
    """Entry point for `cscx browse`."""
    BrowseApp(extra).run()
    return 0
