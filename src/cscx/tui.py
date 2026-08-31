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
from .discovery import Discovered, SearchLocation, discover, installed_applications
from .editors import EDITORS, EditorPaletteError, get_editor
from .emitters import EMITTERS, get_emitter
from .formats import parse_file
from .palette import Palette
from .preview import render, swatch_strip

__all__ = ["BrowseApp", "run"]

#: Where a copied theme goes by default. Discovery scans this directory, so
#: anything written here shows up in the list on the next rescan.
DEFAULT_OUTPUT = Path("~/.config/cscx/themes")


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


class CopyToScreen(ModalScreen[tuple[Target, Path] | None]):
    """Pick a target format and confirm where the file goes."""

    BINDINGS = [Binding("escape", "dismiss_screen", "Cancel")]

    def __init__(self, scheme_name: str) -> None:
        super().__init__()
        self._scheme_name = scheme_name
        self._targets = _targets()
        #: The last path this screen filled in itself. Used to tell an
        #: untouched suggestion from one the user has edited.
        self._suggested = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="copy-dialog"):
            yield Label(f"Copy “{self._scheme_name}” to:", id="copy-title")
            yield OptionList(
                *(Option(t.label, id=t.name) for t in self._targets), id="copy-targets"
            )
            yield Label("Destination", classes="dim")
            yield Input(id="copy-path")
            yield Label("enter writes it · esc cancels", classes="dim")

    def on_mount(self) -> None:
        self.query_one("#copy-targets", OptionList).focus()
        self._sync_path(self._targets[0])

    def _sync_path(self, target: Target) -> None:
        """Suggest a path for `target`, without discarding a typed one.

        Changing the target re-suggests only while the field still holds the
        previous suggestion. Once it has been edited, the edit wins -- silently
        reverting someone's typing is how a file lands somewhere unintended.
        """
        field = self.query_one("#copy-path", Input)
        if field.value and field.value != self._suggested:
            return
        stem = _slugify(self._scheme_name)
        self._suggested = str(
            DEFAULT_OUTPUT.expanduser() / target.filename.format(name=stem)
        )
        field.value = self._suggested

    @on(OptionList.OptionHighlighted, "#copy-targets")
    def _highlight(self, event: OptionList.OptionHighlighted) -> None:
        self._sync_path(self._targets[event.option_index])

    @on(OptionList.OptionSelected, "#copy-targets")
    def _select(self, event: OptionList.OptionSelected) -> None:
        target = self._targets[event.option_index]
        self.dismiss((target, Path(self.query_one("#copy-path", Input).value)))

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
        width: 64; height: auto; padding: 1 2;
        background: $surface; border: thick $primary;
    }
    #copy-targets { height: 12; }
    #activate-dialog {
        width: 88; height: auto; padding: 1 2;
        background: $surface; border: thick $warning;
    }
    #activate-apps { height: 10; }
    #activate-plan { height: auto; padding: 1 0 0 0; color: $text-muted; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("c", "copy_to", "Copy to"),
        Binding("a", "live_apply", "Live"),
        Binding("u", "live_reset", "Undo live"),
        Binding("A", "activate", "Activate"),
        Binding("r", "rescan", "Rescan"),
        Binding("escape", "focus_list", "Back to list", show=False),
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
                yield Input(placeholder="filter…", id="filter")
                yield OptionList(id="schemes")
            with VerticalScroll(id="preview-pane"):
                yield Static("", id="preview")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"cscx {__version__}"
        self.action_rescan()
        # The list takes focus, not the filter: single-key bindings like `c`
        # and `r` would otherwise be typed into the filter field instead.
        self.query_one("#schemes", OptionList).focus()

    # -- data ------------------------------------------------------------

    def action_rescan(self) -> None:
        self._all = discover(self._extra, locations=self._locations)
        self._cache.clear()
        self._refresh_in_use()
        self._apply_filter(self.query_one("#filter", Input).value)
        self.sub_title = f"{len(self._all)} schemes"

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
        needle = needle.strip().lower()
        self._shown = [
            d for d in self._all
            if not needle or needle in d.name.lower() or needle in d.format
        ]

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
        row.append(f"  {found.format}", style="dim")
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

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_focus_list(self) -> None:
        self.query_one("#schemes", OptionList).focus()

    def action_copy_to(self) -> None:
        if not (found := self.current()):
            return
        # Name the file after the scheme's own name where it has one -- konsole
        # records a Description, for instance -- so the filename and the name
        # written inside the file agree.
        try:
            name = self._palette(found.path).name or found.name
        except Exception:
            name = found.name
        self.push_screen(CopyToScreen(name), self._write_copy)

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
