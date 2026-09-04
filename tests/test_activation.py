"""Activation: the one part that edits configuration you did not create.

Every test here runs against a sandboxed HOME, so nothing can reach the real
configuration even if a path is built wrongly.
"""

import tomllib
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.activation import (
    MARKER,
    ActivationError,
    Plan,
    Step,
    apply_plan,
    plan,
)
from cscx.activation import _alacritty_import, _konsole_profile, _managed_line

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A throwaway HOME, with XDG overrides cleared."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return tmp_path


@pytest.fixture
def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


# -- the managed line -----------------------------------------------------


def test_managed_line_is_appended_with_its_marker():
    result = _managed_line("font_size 11\n", "include themes/x.conf")
    assert MARKER in result
    assert result.rstrip().endswith("include themes/x.conf")


def test_managed_line_is_rewritten_not_duplicated():
    """Activating twice must leave one include, not two."""
    once = _managed_line("font_size 11\n", "include themes/a.conf")
    twice = _managed_line(once, "include themes/b.conf")

    assert twice.count(MARKER) == 1
    assert "include themes/a.conf" not in twice
    assert "include themes/b.conf" in twice


def test_managed_line_leaves_the_rest_of_the_file_alone():
    original = "font_size 11\n# a comment\nbackground #000000\n"
    result = _managed_line(original, "include themes/x.conf")
    for line in original.splitlines():
        assert line in result


def test_managed_line_handles_a_marker_at_end_of_file():
    result = _managed_line(f"font_size 11\n{MARKER}", "include themes/x.conf")
    assert result.rstrip().endswith("include themes/x.conf")


# -- alacritty's TOML -----------------------------------------------------


def test_alacritty_replaces_an_existing_import():
    source = '[general]\nimport = ["old.toml"]\n\n[font]\nsize = 11.0\n'
    result = _alacritty_import(source, Path("/new.toml"))

    assert 'import = ["/new.toml"]' in result
    assert "old.toml" not in result
    assert tomllib.loads(result)["general"]["import"] == ["/new.toml"]
    assert tomllib.loads(result)["font"]["size"] == 11.0


def test_alacritty_adds_import_to_an_existing_general_table():
    result = _alacritty_import("[general]\nlive_config_reload = true\n", Path("/x.toml"))
    document = tomllib.loads(result)
    assert document["general"]["import"] == ["/x.toml"]
    assert document["general"]["live_config_reload"] is True


def test_alacritty_creates_general_when_there_is_none():
    result = _alacritty_import("[font]\nsize = 11.0\n", Path("/x.toml"))
    assert tomllib.loads(result)["general"]["import"] == ["/x.toml"]


def test_alacritty_never_writes_a_second_general_table():
    """A duplicate table is a TOML error, not merely untidy."""
    once = _alacritty_import("[general]\nimport = []\n", Path("/a.toml"))
    twice = _alacritty_import(once, Path("/b.toml"))

    assert twice.count("[general]") == 1
    assert tomllib.loads(twice)["general"]["import"] == ["/b.toml"]


def test_alacritty_does_not_touch_a_later_tables_import():
    source = '[font]\nsize = 11.0\n\n[general]\nimport = ["a.toml"]\n'
    result = _alacritty_import(source, Path("/b.toml"))
    assert tomllib.loads(result)["general"]["import"] == ["/b.toml"]


# -- konsole profiles -----------------------------------------------------


def test_konsole_replaces_the_colour_scheme():
    source = "[Appearance]\nColorScheme=Old\nDimmValue=15\n"
    result = _konsole_profile(source, "New")
    assert "ColorScheme=New" in result
    assert "ColorScheme=Old" not in result
    assert "DimmValue=15" in result


def test_konsole_inserts_into_an_appearance_section_without_one():
    result = _konsole_profile("[Appearance]\nDimmValue=15\n\n[General]\nName=x\n", "New")
    assert "ColorScheme=New" in result
    assert result.index("ColorScheme=New") < result.index("[General]")


def test_konsole_creates_the_section_when_absent():
    result = _konsole_profile("[General]\nName=x\n", "New")
    assert "[Appearance]" in result and "ColorScheme=New" in result


# -- plans ----------------------------------------------------------------


@pytest.mark.parametrize("app", ["kitty", "alacritty", "foot", "ghostty"])
def test_terminal_plans_write_a_theme_and_edit_the_config(home, gruvbox, app):
    proposed = plan(gruvbox, app, name="Test")
    assert proposed.app == app
    assert len(proposed.steps) == 2
    assert all(str(home) in str(step.path) for step in proposed.steps)
    assert proposed.reload


def test_editor_plans_never_edit_an_existing_config(home, gruvbox):
    """Placing a theme file is safe; rewriting someone's init is not."""
    for app in ("vim", "neovim", "helix", "emacs"):
        proposed = plan(gruvbox, app, name="Test")
        assert not any(step.edits_existing for step in proposed.steps)


def test_vscode_plan_includes_the_extension_manifest(home, gruvbox):
    proposed = plan(gruvbox, "vscode", name="Test")
    names = {step.path.name for step in proposed.steps}
    assert names == {"package.json", "test-color-theme.json"}


def test_vscode_manifest_matches_the_scheme_lightness(home, gruvbox):
    import json

    dark = plan(gruvbox, "vscode", name="Test")
    manifest = json.loads(next(s.content for s in dark.steps if s.path.name == "package.json"))
    assert manifest["contributes"]["themes"][0]["uiTheme"] == "vs-dark"

    gruvbox.background, gruvbox.foreground = gruvbox.foreground, gruvbox.background
    light = plan(gruvbox, "vscode", name="Test")
    manifest = json.loads(next(s.content for s in light.steps if s.path.name == "package.json"))
    assert manifest["contributes"]["themes"][0]["uiTheme"] == "vs"


def test_konsole_without_a_profile_says_it_is_not_selected(home, gruvbox):
    proposed = plan(gruvbox, "konsole", name="Test")
    assert len(proposed.steps) == 1
    assert any("not selected" in w for w in proposed.warnings)


def test_konsole_with_a_profile_points_it_at_the_scheme(home, gruvbox, tmp_path):
    profile = tmp_path / "Default.profile"
    profile.write_text("[Appearance]\nColorScheme=Old\n")

    proposed = plan(gruvbox, "konsole", name="Test", profile=profile)
    assert len(proposed.steps) == 2
    assert not proposed.warnings
    assert "ColorScheme=test" in proposed.steps[1].content


def test_plans_honour_xdg_config_home(tmp_path, monkeypatch, gruvbox):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    for app in ("kitty", "neovim", "helix"):
        proposed = plan(gruvbox, app, name="Test")
        assert all(str(tmp_path / "xdg") in str(s.path) for s in proposed.steps), app


def test_an_unknown_application_is_refused(home, gruvbox):
    with pytest.raises(ActivationError, match="cannot activate"):
        plan(gruvbox, "notepad")


# -- applying -------------------------------------------------------------


def test_apply_creates_files_and_backs_up_what_it_edits(home, gruvbox):
    config = home / ".config/kitty/kitty.conf"
    config.parent.mkdir(parents=True)
    config.write_text("font_size 11\n")

    backups = apply_plan(plan(gruvbox, "kitty", name="Test"), validate=False)

    assert (home / ".config/kitty/themes/test.conf").is_file()
    assert "include themes/test.conf" in config.read_text()
    assert len(backups) == 1
    assert backups[0].read_text() == "font_size 11\n"


def test_apply_is_idempotent(home, gruvbox):
    config = home / ".config/kitty/kitty.conf"
    config.parent.mkdir(parents=True)
    config.write_text("font_size 11\n")

    apply_plan(plan(gruvbox, "kitty", name="One"), validate=False)
    apply_plan(plan(gruvbox, "kitty", name="Two"), validate=False)

    text = config.read_text()
    assert text.count(MARKER) == 1
    assert text.count("include themes/") == 1
    assert "include themes/two.conf" in text


def test_backups_never_overwrite_one_another(home, gruvbox):
    """Two activations in the same second must not lose the original."""
    config = home / ".config/kitty/kitty.conf"
    config.parent.mkdir(parents=True)
    config.write_text("original\n")

    first = apply_plan(plan(gruvbox, "kitty", name="One"), validate=False)
    second = apply_plan(plan(gruvbox, "kitty", name="Two"), validate=False)

    assert first[0] != second[0]
    assert first[0].read_text() == "original\n"


def test_a_rejected_result_is_rolled_back(home):
    config = home / ".config/alacritty/alacritty.toml"
    config.parent.mkdir(parents=True)
    original = '[general]\nimport = ["keep.toml"]\n'
    config.write_text(original)
    theme = home / ".config/alacritty/themes/broken.toml"

    broken = Plan(app="alacritty", steps=[
        Step(theme, "this = is = not = toml\n", "the theme itself"),
        Step(config, "[general\n", "import the theme", True),
    ])

    with pytest.raises(ActivationError, match="not valid TOML"):
        apply_plan(broken)

    assert config.read_text() == original
    assert not theme.exists()


def test_validation_can_be_skipped(home):
    config = home / ".config/alacritty/alacritty.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[general]\n")

    Path(home / ".config/alacritty/themes").mkdir(parents=True)
    broken = Plan(app="alacritty", steps=[
        Step(config, "not = = toml\n", "import the theme", True),
    ])
    apply_plan(broken, validate=False)
    assert config.read_text() == "not = = toml\n"


def test_backups_can_be_declined(home, gruvbox):
    config = home / ".config/kitty/kitty.conf"
    config.parent.mkdir(parents=True)
    config.write_text("font_size 11\n")

    assert apply_plan(plan(gruvbox, "kitty", name="Test"), backup=False, validate=False) == []
    assert not list(config.parent.glob("*.bak"))


def test_activating_into_an_empty_home_creates_the_config(home, gruvbox):
    apply_plan(plan(gruvbox, "foot", name="Test"), validate=False)
    config = home / ".config/foot/foot.ini"
    assert config.is_file()
    assert "include=" in config.read_text()
    assert (home / ".config/foot/themes/test.ini").is_file()


def test_a_plan_says_where_the_theme_itself_goes(home, gruvbox):
    """`browse`'s copy needs this without matching on the description prose."""
    for app, expected in (
        ("kitty", ".config/kitty/themes"),
        ("claude-code", ".claude/themes"),
        ("konsole", ".local/share/konsole"),
        ("neovim", ".config/nvim/colors"),
    ):
        path = plan(gruvbox, app, name="Test").theme_path
        assert path is not None and expected in str(path), app


def test_the_theme_step_is_not_the_config_edit(home, gruvbox):
    proposed = plan(gruvbox, "kitty", name="Test")
    theme = [step for step in proposed.steps if step.is_theme]
    assert len(theme) == 1
    assert not theme[0].edits_existing
    assert proposed.theme_path == theme[0].path


def test_vscode_points_at_the_theme_not_the_manifest(home, gruvbox):
    assert plan(gruvbox, "vscode", name="Test").theme_path.name.endswith(
        "-color-theme.json"
    )
