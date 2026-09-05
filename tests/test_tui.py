"""The browse TUI, driven headlessly through Textual's test pilot."""

from pathlib import Path

import pytest

pytest.importorskip("textual", reason="the TUI is an optional extra")

from cscx.discovery import SearchLocation          # noqa: E402
from cscx.tui import BrowseApp, _targets           # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
#: Pinned so the tests do not depend on what is installed on the machine.
ONLY_FIXTURES = [SearchLocation("fixtures", FIXTURES, ("*",), None)]


def make_app() -> BrowseApp:
    return BrowseApp(locations=ONLY_FIXTURES)


@pytest.mark.asyncio
async def test_the_app_lists_what_discovery_found():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert len(app._all) >= 10
        assert len(app._shown) == len(app._all)
        assert app.query_one("#schemes").option_count == len(app._all)


@pytest.mark.asyncio
async def test_a_scheme_is_previewed_on_highlight():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "comments" in app.preview_text
        assert ":1 vs background" in app.preview_text


@pytest.mark.asyncio
async def test_moving_through_the_list_changes_the_preview():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        first_scheme, first_preview = app.current(), app.preview_text

        # Jump to a different format rather than stepping one row: the
        # alacritty .toml and .yml fixtures hold the same scheme under the
        # same stem, so their previews are identical by design.
        options = app.query_one("#schemes")
        options.highlighted = next(
            i for i, d in enumerate(app._shown) if d.format == "konsole"
        )
        await pilot.pause()

        assert app.current() != first_scheme
        assert app.preview_text != first_preview
        assert "konsole" in app.preview_text


@pytest.mark.asyncio
async def test_filtering_narrows_the_list():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        total = len(app._shown)
        app.query_one("#filter").value = "konsole"
        await pilot.pause()
        assert 0 < len(app._shown) < total
        assert all(d.format == "konsole" for d in app._shown)


@pytest.mark.asyncio
async def test_a_filter_matching_nothing_says_so():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#filter").value = "zzzz-no-such-scheme"
        await pilot.pause()
        assert app._shown == []
        assert "no scheme matches" in app.preview_text
        assert app.current() is None


@pytest.mark.asyncio
async def test_copy_to_writes_the_chosen_target(tmp_path):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#filter").value = "kitty"
        await pilot.pause()
        app.query_one("#schemes").focus()
        await pilot.pause()

        await pilot.press("c")
        await pilot.pause()

        # Choose ghostty explicitly rather than relying on list order.
        targets = app.screen.query_one("#copy-targets")
        targets.highlighted = [t.name for t in app.screen._targets].index("ghostty")
        await pilot.pause()

        destination = tmp_path / "copied.ghostty"
        app.screen.query_one("#copy-path").value = str(destination)
        await pilot.press("enter")
        await pilot.pause()

        assert app.written == [destination]
        assert "palette = 0=" in destination.read_text()


@pytest.mark.asyncio
async def test_changing_target_does_not_discard_an_edited_path(tmp_path):
    """Silently reverting a typed path is how a file lands somewhere wrong."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        field = app.screen.query_one("#copy-path")
        assert field.value, "no path was suggested"

        typed = str(tmp_path / "mine.conf")
        field.value = typed
        for _ in range(3):
            await pilot.press("down")
        await pilot.pause()
        assert field.value == typed


@pytest.mark.asyncio
async def test_an_untouched_suggestion_follows_the_target():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        field = app.screen.query_one("#copy-path")
        first = field.value
        await pilot.press("down")
        await pilot.pause()
        assert field.value != first


@pytest.mark.asyncio
async def test_escape_cancels_without_writing():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.written == []
        assert type(app.screen).__name__ != "CopyToScreen"


@pytest.mark.asyncio
async def test_rescan_reloads_the_list():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        before = len(app._all)
        await pilot.press("r")
        await pilot.pause()
        assert len(app._all) == before


def test_every_convertible_target_is_offered():
    from cscx.editors import EDITORS
    from cscx.emitters import EMITTERS

    offered = {t.name for t in _targets()}
    assert offered == set(EMITTERS) | set(EDITORS)


# -- live preview ---------------------------------------------------------


@pytest.fixture
def fake_terminal(monkeypatch):
    """Capture what would be written to the terminal instead of writing it."""
    from cscx import live

    written: list[str] = []
    monkeypatch.setattr(live, "is_supported", lambda: True)
    monkeypatch.setattr(live, "_write", lambda payload: written.append(payload) or True)
    return written


@pytest.mark.asyncio
async def test_a_applies_the_scheme_to_the_terminal(fake_terminal):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app.live_scheme is not None
        assert fake_terminal and "\x1b]4;0;rgb:" in fake_terminal[0]


@pytest.mark.asyncio
async def test_u_restores_the_terminal(fake_terminal):
    from cscx import live

    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert app.live_scheme is None
        assert fake_terminal[-1] == live.reset_sequences()


@pytest.mark.asyncio
async def test_quitting_restores_a_live_preview(fake_terminal):
    """Leaving the terminal recoloured after quitting would be rude."""
    from cscx import live

    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app.live_scheme is not None

    assert fake_terminal[-1] == live.reset_sequences()


@pytest.mark.asyncio
async def test_no_terminal_is_reported_rather_than_crashing(monkeypatch):
    from cscx import live

    monkeypatch.setattr(live, "is_supported", lambda: False)
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app.live_scheme is None


# -- activation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_screen_shows_the_plan_before_applying(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()

        assert type(app.screen).__name__ == "ActivateScreen"
        plan_text = str(app.screen.query_one("#activate-plan").renderable
                        if hasattr(app.screen.query_one("#activate-plan"), "renderable")
                        else app.screen._apps)
        assert plan_text            # a plan (or app list) was rendered
        assert app.activated == []  # nothing applied merely by looking


@pytest.mark.asyncio
async def test_activation_writes_the_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()

        apps = app.screen.query_one("#activate-apps")
        apps.highlighted = app.screen._apps.index("helix")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert app.activated == ["helix"]
        assert list((tmp_path / ".config/helix/themes").glob("*.toml"))


@pytest.mark.asyncio
async def test_escape_leaves_activation_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.activated == []
        assert not (tmp_path / ".config").exists()


@pytest.mark.asyncio
async def test_installed_applications_are_offered_first(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()

        from cscx.discovery import installed_applications
        from cscx.activation import ACTIVATABLE

        installed = installed_applications() & set(ACTIVATABLE)
        offered = app.screen._apps
        if installed:
            assert offered[0] in installed


# -- "in use" markers -----------------------------------------------------


@pytest.mark.asyncio
async def test_schemes_in_use_are_marked(monkeypatch):
    """The list should say which discovered scheme a terminal is actually on."""
    import cscx.tui as tui
    from cscx.active import Active

    target = (FIXTURES / "gruvbox.kitty.conf").resolve()
    monkeypatch.setattr(
        tui, "detect_active",
        lambda **kwargs: [Active("kitty", "terminal", "gruvbox", target, "test")],
    )

    app = make_app()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert app.in_use == {target: ["kitty"]}

        index = next(i for i, found in enumerate(app._shown) if found.path == target)
        options = app.query_one("#schemes")
        assert options.get_option_at_index(index).prompt.plain.endswith("●")

        # The prose lives in the status line, which is as wide as the window.
        options.highlighted = index
        await pilot.pause()
        assert "in use by kitty" in str(app.query_one("#status").render())


@pytest.mark.asyncio
async def test_a_failing_probe_leaves_the_list_usable(monkeypatch):
    """Detection is a nicety; it must never cost you the browser."""
    import cscx.tui as tui

    def explode(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(tui, "detect_active", explode)
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.in_use == {}
        assert app._shown


@pytest.mark.asyncio
async def test_filtering_by_source():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#filter").value = "source:fixtures"
        await pilot.pause()
        assert app._shown == app._all

        app.query_one("#filter").value = "source:nothing-like-this"
        await pilot.pause()
        assert app._shown == []


@pytest.mark.asyncio
async def test_the_filter_is_fuzzy():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # `grvbx` is not a substring of anything, but it is a subsequence.
        app.query_one("#filter").value = "grvbx"
        await pilot.pause()
        assert app._shown
        assert all("gruvbox" in d.path.name for d in app._shown)


@pytest.mark.asyncio
async def test_rows_show_the_source_not_the_container_format():
    app = make_app()
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        row = app.query_one("#schemes").get_option_at_index(0).prompt
        assert "fixtures" in row.plain


# -- vim navigation -------------------------------------------------------


@pytest.mark.asyncio
async def test_j_and_k_move_through_the_list():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        first = app.current()

        await pilot.press("j")
        await pilot.pause()
        second = app.current()
        assert second != first

        await pilot.press("k")
        await pilot.pause()
        assert app.current() == first


@pytest.mark.asyncio
async def test_arrow_keys_still_work():
    """hjkl is an addition, not a replacement."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        first = app.current()
        await pilot.press("down")
        await pilot.pause()
        assert app.current() != first


@pytest.mark.asyncio
async def test_g_and_shift_g_jump_to_the_ends():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert app.current() == app._shown[-1]

        await pilot.press("g")
        await pilot.pause()
        assert app.current() == app._shown[0]


@pytest.mark.asyncio
async def test_navigation_stops_at_the_ends():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for _ in range(5):
            await pilot.press("k")          # already at the top
        await pilot.pause()
        assert app.current() == app._shown[0]

        for _ in range(len(app._shown) + 5):
            await pilot.press("j")
        await pilot.pause()
        assert app.current() == app._shown[-1]


@pytest.mark.asyncio
async def test_ctrl_d_and_ctrl_u_move_further_than_one_row():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+d")
        await pilot.pause()
        moved = app.query_one("#schemes").highlighted
        assert moved > 1

        await pilot.press("ctrl+u")
        await pilot.pause()
        assert app.query_one("#schemes").highlighted == 0


@pytest.mark.asyncio
async def test_l_moves_into_the_preview_and_h_comes_back():
    from textual.containers import VerticalScroll
    from textual.widgets import OptionList

    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.focused, VerticalScroll)

        await pilot.press("h")
        await pilot.pause()
        assert isinstance(app.focused, OptionList)


@pytest.mark.asyncio
async def test_j_scrolls_the_preview_once_it_has_focus():
    """Otherwise `l` then `j` would silently move the list behind the preview."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        selected = app.current()

        await pilot.press("l")
        await pilot.pause()
        for _ in range(3):
            await pilot.press("j")
        await pilot.pause()

        assert app.current() == selected


@pytest.mark.asyncio
async def test_letters_typed_into_the_filter_are_not_navigation():
    """The filter must accept j, k, g and q as text."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one("#filter").focus()
        await pilot.press("j", "k", "g", "q")
        await pilot.pause()
        assert app.query_one("#filter").value == "jkgq"
        assert app.is_running


# -- help -----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["question_mark", "f1"])
async def test_help_opens_on_question_mark_and_f1(key):
    app = make_app()
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        assert type(app.screen).__name__ == "HelpScreen"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["escape", "question_mark", "f1", "q"])
async def test_help_closes_on_any_of_its_keys(key):
    app = make_app()
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        assert type(app.screen).__name__ != "HelpScreen"
        assert app.is_running, "q inside help should close it, not quit cscx"


@pytest.mark.asyncio
async def test_help_does_not_disturb_the_selection():
    app = make_app()
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        await pilot.press("j")
        await pilot.pause()
        selected = app.current()

        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.current() == selected


@pytest.mark.asyncio
async def test_question_mark_typed_into_the_filter_is_text():
    app = make_app()
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        app.query_one("#filter").focus()
        await pilot.press("question_mark")
        await pilot.pause()
        assert type(app.screen).__name__ != "HelpScreen"
        assert app.query_one("#filter").value == "?"


#: How a binding's key name is spelled for a human, so the drift guard can
#: recognise it in the help text.
_SPELLING = {"question_mark": "?", "slash": "/", "f1": "F1"}


def test_every_binding_is_documented_in_the_help():
    """A key that works but is not in the help is a key nobody finds."""
    from cscx.tui import HELP, BrowseApp

    import re

    documented = set()
    for _section, rows in HELP:
        for keys, _description in rows:
            # Split on " / " and " or " as separators, which leaves a bare "/"
            # -- itself a binding -- intact.
            for token in re.split(r"\s+or\s+|\s+/\s+", keys):
                if token.strip():
                    documented.add(token.strip())

    for binding in BrowseApp.BINDINGS:
        if not binding.description:
            continue
        for key in binding.key.split(","):
            spelled = _SPELLING.get(key.strip(), key.strip())
            assert spelled in documented, f"{spelled!r} is bound but undocumented"


def test_the_help_explains_the_filter_syntax():
    from cscx.tui import HELP

    text = " ".join(
        f"{keys} {description}"
        for _section, rows in HELP for keys, description in rows
    )
    assert "source:" in text and "fuzzil" in text.lower()


def test_the_help_explains_what_the_list_shows():
    """The swatches, the source column and the in-use dot are not obvious."""
    from cscx.tui import HELP

    text = " ".join(
        description for _section, rows in HELP for _keys, description in rows
    )
    assert "source" in text and "in use" in text.lower() or "currently using" in text


# -- the copy dialog ------------------------------------------------------
#
# `test_every_convertible_target_is_offered` checks the model and passed while
# the dialog showed ten of seventeen targets with nothing to say so. These
# check what a person can actually reach.


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(120, 40), (100, 30), (100, 24), (90, 20)])
async def test_any_target_is_reachable_however_short_the_terminal(size):
    from cscx.editors import EDITORS
    from cscx.emitters import EMITTERS

    app = make_app()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        for name in sorted(set(EMITTERS) | set(EDITORS)):
            app.screen.query_one("#copy-filter").value = name
            await pilot.pause()
            shown = [t.name for t in app.screen._shown]
            assert name in shown, f"{name} unreachable at {size}"
            assert app.screen.highlighted() is not None


@pytest.mark.asyncio
async def test_the_filter_takes_focus_so_typing_narrows():
    app = make_app()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert app.screen.focused.id == "copy-filter"

        for char in "claude":
            await pilot.press(char)
        await pilot.pause()
        assert [t.name for t in app.screen._shown] == ["claude-code"]


@pytest.mark.asyncio
async def test_up_and_down_drive_the_list_from_the_filter():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        first = app.screen.highlighted()

        await pilot.press("down")
        await pilot.pause()
        assert app.screen.highlighted() != first

        await pilot.press("up")
        await pilot.pause()
        assert app.screen.highlighted() == first


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,expected",
    [
        ("claude-code", ".claude/themes"),
        ("neovim", ".config/nvim/colors"),
        ("kitty", ".config/kitty/themes"),
        ("konsole", ".local/share/konsole"),
    ],
)
async def test_the_destination_is_where_that_application_looks(target, expected):
    """A theme written where the program never looks does nothing at all."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#copy-filter").value = target
        await pilot.pause()
        assert expected in app.screen.query_one("#copy-path").value


@pytest.mark.asyncio
async def test_targets_with_no_conventional_home_fall_back_to_the_cscx_directory():
    """iTerm2 and friends have no single place a theme belongs."""
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#copy-filter").value = "iterm2"
        await pilot.pause()
        assert ".config/cscx/themes" in app.screen.query_one("#copy-path").value


@pytest.mark.asyncio
async def test_copying_to_claude_code_writes_a_theme_claude_code_would_load(tmp_path):
    import json

    from tests.test_claude_code import CLAUDE_CODE_TOKENS

    app = make_app()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        app.screen.query_one("#copy-filter").value = "claude-code"
        await pilot.pause()

        destination = tmp_path / "argonaut.json"
        app.screen.query_one("#copy-path").value = str(destination)
        await pilot.press("enter")
        await pilot.pause()

    document = json.loads(destination.read_text())
    assert set(document) == {"name", "base", "overrides"}
    assert not set(document["overrides"]) - CLAUDE_CODE_TOKENS


@pytest.mark.asyncio
async def test_the_copy_destination_is_shown_tilde_abbreviated(tmp_path, monkeypatch):
    """The field is a fixed width; `/home/somebody` is a prefix every row shares."""
    monkeypatch.setenv("HOME", str(tmp_path))
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        value = app.screen.query_one("#copy-path").value

    assert value.startswith("~/"), value
    assert str(tmp_path) not in value


@pytest.mark.asyncio
async def test_a_typed_tilde_is_expanded_not_taken_literally(tmp_path, monkeypatch):
    """`~/themes/x.conf` used to become a directory called `~` in the cwd."""
    monkeypatch.setenv("HOME", str(tmp_path))
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        screen = app.screen
        screen.query_one("#copy-path").value = "~/themes/typed.conf"
        result = None

        def capture(value):
            nonlocal result
            result = value

        screen.dismiss = capture           # type: ignore[method-assign]
        screen._confirm(screen.highlighted())

    assert result is not None
    _target, destination = result
    assert destination == tmp_path / "themes/typed.conf"
    assert "~" not in str(destination)


@pytest.mark.asyncio
async def test_a_long_name_is_cut_to_the_sidebar_rather_than_wrapping(tmp_path):
    """A wrapped row makes the list unreadable, and base16 names are long.

    Textual's OptionList wraps its options and ignores `no_wrap` on a Rich
    Text, so the row has to be cut to length when it is built.
    """
    source = (FIXTURES / "gruvbox.kitty.conf").read_text()
    (tmp_path / "base16-atelier-sulphurpool-light.conf").write_text(source)
    (tmp_path / "x.conf").write_text(source)
    locations = [SearchLocation("t", tmp_path, ("*.conf",), "kitty")]

    # Narrow enough that the source label has to go, wide enough that it fits.
    for width in (70, 124, 200):
        app = BrowseApp(locations=locations)
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()
            options = app.query_one("#schemes")
            available = options.content_size.width
            rows = [options.get_option_at_index(i).prompt.plain
                    for i in range(options.option_count)]

        assert len(rows) == 2
        for row in rows:
            assert len(row) <= available, (width, repr(row))
        assert any("…" in row for row in rows), (width, rows)


@pytest.mark.asyncio
async def test_rows_are_rebuilt_when_the_window_changes_width(tmp_path):
    """Cut once at the wrong width, they stay cut at the wrong width."""
    source = (FIXTURES / "gruvbox.kitty.conf").read_text()
    (tmp_path / "base16-atelier-sulphurpool-light.conf").write_text(source)
    locations = [SearchLocation("t", tmp_path, ("*.conf",), "kitty")]

    app = BrowseApp(locations=locations)
    async with app.run_test(size=(70, 30)) as pilot:
        await pilot.pause()
        options = app.query_one("#schemes")
        narrow = options.get_option_at_index(0).prompt.plain

        await pilot.resize_terminal(200, 30)
        await pilot.pause()
        await pilot.pause()
        wide = options.get_option_at_index(0).prompt.plain

    assert len(wide) > len(narrow)
    assert "sulphurpool" in wide and "sulphurpool" not in narrow
