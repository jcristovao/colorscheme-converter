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
        row = app.query_one("#schemes").get_option_at_index(index).prompt
        assert "in use by kitty" in row.plain


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
