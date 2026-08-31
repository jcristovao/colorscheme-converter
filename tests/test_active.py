"""Detecting which scheme each application is currently using."""

import shutil
from pathlib import Path

import pytest

from cscx._text import strip_jsonc
from cscx.active import Active, detect, detect_one, palette_of
from cscx.active import _last_directive

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return tmp_path


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# -- JSONC ----------------------------------------------------------------


def test_strip_jsonc_keeps_urls_inside_strings():
    """The bug this replaced: `//` in a URL truncated the line."""
    source = '{"a": "file:///home/me/x.json", "b": 1}'
    assert strip_jsonc(source) == source


def test_strip_jsonc_removes_real_comments():
    source = '{\n  // a comment\n  "a": 1  // trailing\n}'
    assert "comment" not in strip_jsonc(source)
    assert '"a": 1' in strip_jsonc(source)


def test_strip_jsonc_removes_block_comments():
    assert "gone" not in strip_jsonc('{/* gone */ "a": 1}')


def test_strip_jsonc_removes_trailing_commas_only():
    assert strip_jsonc('{"a": [1, 2,], }') == '{"a": [1, 2] }'
    # A comma inside a string is not a trailing comma.
    assert strip_jsonc('{"a": "x,}"}') == '{"a": "x,}"}'


def test_strip_jsonc_handles_escaped_quotes():
    source = r'{"a": "he said \"hi\" // not a comment"}'
    assert strip_jsonc(source) == source


# -- ordering in kitty/foot style configs ---------------------------------


def test_a_later_include_wins(tmp_path):
    write(tmp_path / "a.conf", "color0 #111111\n")
    write(tmp_path / "b.conf", "color0 #222222\n")
    config = "include a.conf\ninclude b.conf\n"

    winner, inline_wins = _last_directive(config, tmp_path)
    assert winner == tmp_path / "b.conf"
    assert not inline_wins


def test_inline_colours_after_an_include_win(tmp_path):
    """A naive grep reports the include; the terminal uses the inline value."""
    write(tmp_path / "a.conf", "color0 #111111\n")
    winner, inline_wins = _last_directive("include a.conf\ncolor0 #333333\n", tmp_path)
    assert winner == tmp_path / "a.conf"
    assert inline_wins


def test_an_include_after_inline_colours_wins(tmp_path):
    write(tmp_path / "a.conf", "color0 #111111\n")
    _, inline_wins = _last_directive("color0 #333333\ninclude a.conf\n", tmp_path)
    assert not inline_wins


def test_a_missing_include_is_ignored(tmp_path):
    winner, _ = _last_directive("include nope.conf\n", tmp_path)
    assert winner is None


def test_commented_includes_are_ignored(tmp_path):
    write(tmp_path / "a.conf", "color0 #111111\n")
    winner, _ = _last_directive("# include a.conf\n", tmp_path)
    assert winner is None


def test_absolute_and_tilde_includes_resolve(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = write(tmp_path / "themes/x.ini", "background=282828\n")

    absolute, _ = _last_directive(f"include={target}\n", tmp_path)
    assert absolute == target

    tilde, _ = _last_directive("include=~/themes/x.ini\n", tmp_path)
    assert tilde == target


# -- per application ------------------------------------------------------


def test_kitty_reports_the_included_theme(home):
    write(home / ".config/kitty/themes/mine.conf", "color0 #111111\n")
    write(home / ".config/kitty/kitty.conf", "font_size 11\ninclude themes/mine.conf\n")

    entry = detect_one("kitty")[0]
    assert entry.name == "mine"
    assert entry.path == home / ".config/kitty/themes/mine.conf"


def test_kitty_says_so_when_inline_colours_win(home):
    write(home / ".config/kitty/themes/mine.conf", "color0 #111111\n")
    write(home / ".config/kitty/kitty.conf",
          "include themes/mine.conf\ncolor0 #333333\n")

    entry = detect_one("kitty")[0]
    assert entry.name == "(inline)"
    assert "inline values win" in entry.note


def test_alacritty_reports_the_last_import(home):
    write(home / ".config/alacritty/themes/one.toml", "[colors.primary]\n")
    write(home / ".config/alacritty/themes/two.toml", "[colors.primary]\n")
    write(home / ".config/alacritty/alacritty.toml",
          '[general]\nimport = ["themes/one.toml", "themes/two.toml"]\n')

    entry = detect_one("alacritty")[0]
    assert entry.name == "two"


def test_alacritty_falls_back_to_inline_colours(home):
    write(home / ".config/alacritty/alacritty.toml",
          "[colors.primary]\nbackground = '#282828'\n")
    assert detect_one("alacritty")[0].name == "(inline)"


def test_alacritty_survives_a_broken_config(home):
    write(home / ".config/alacritty/alacritty.toml", "[general\n")
    entry = detect_one("alacritty")[0]
    assert entry.name is None
    assert "unreadable" in entry.source


def test_ghostty_resolves_a_named_theme(home):
    write(home / ".config/ghostty/themes/mine", "background = #282828\n")
    write(home / ".config/ghostty/config", "theme = mine\n")

    entry = detect_one("ghostty")[0]
    assert entry.name == "mine"
    assert entry.path == home / ".config/ghostty/themes/mine"


def test_ghostty_reports_a_named_theme_it_cannot_find(home):
    write(home / ".config/ghostty/config", "theme = missing\n")
    entry = detect_one("ghostty")[0]
    assert entry.name == "missing"
    assert entry.path is None
    assert "not found" in entry.note


def test_konsole_answers_once_per_profile(home):
    write(home / ".local/share/konsole/A.profile", "[Appearance]\nColorScheme=One\n")
    write(home / ".local/share/konsole/B.profile", "[Appearance]\nColorScheme=Two\n")
    write(home / ".local/share/konsole/One.colorscheme", "[Background]\nColor=0,0,0\n")

    entries = detect_one("konsole")
    assert {e.name for e in entries} == {"One", "Two"}
    assert all("no default profile" in e.note for e in entries)


def test_konsole_marks_the_default_profile(home):
    write(home / ".local/share/konsole/A.profile", "[Appearance]\nColorScheme=One\n")
    write(home / ".local/share/konsole/B.profile", "[Appearance]\nColorScheme=Two\n")
    write(home / ".config/konsolerc", "[Desktop Entry]\nDefaultProfile=A.profile\n")

    entries = {e.name: e for e in detect_one("konsole")}
    assert entries["One"].note == "default profile"
    assert entries["Two"].note == ""


def test_vscode_reads_the_colour_theme(home):
    write(home / ".config/Code - OSS/User/settings.json",
          '{\n  // theme\n  "workbench.colorTheme": "Kimbie Dark",\n}')
    assert detect_one("vscode")[0].name == "Kimbie Dark"


def test_vscode_settings_containing_a_url_still_parse(home):
    """Regression: a `file:///` URL used to break the comment stripper."""
    write(home / ".config/Code - OSS/User/settings.json",
          '{\n  "workbench.colorTheme": "Kimbie Dark",\n'
          '  "json.schemas": {"file:///home/me/x.json": "y.yml"}\n}')
    assert detect_one("vscode")[0].name == "Kimbie Dark"


def test_vscode_reports_a_settings_file_it_cannot_parse(home):
    write(home / ".config/Code - OSS/User/settings.json", "{not json")
    entry = detect_one("vscode")[0]
    assert entry.name is None
    assert "could not be parsed" in entry.note


def test_helix_reads_its_theme(home):
    write(home / ".config/helix/config.toml", 'theme = "gruvbox"\n')
    assert detect_one("helix")[0].name == "gruvbox"


def test_emacs_finds_a_loaded_theme(home):
    write(home / ".emacs.d/init.el", ";; init\n(load-theme 'gruvbox t)\n")
    assert detect_one("emacs")[0].name == "gruvbox"


# -- the whole sweep ------------------------------------------------------


def test_absent_applications_are_left_out(home):
    """An empty home should produce no rows for things that are not set up."""
    for entry in detect(editors=False):
        assert entry.name is not None


def test_detect_can_skip_the_editors(home):
    assert all(e.kind == "terminal" for e in detect(editors=False))


def test_a_failing_probe_does_not_sink_the_rest(home, monkeypatch):
    import cscx.active as module

    def explode():
        raise RuntimeError("boom")

    monkeypatch.setitem(module._DETECTORS, "kitty", explode)
    entries = detect_one("kitty")
    assert entries[0].name is None
    assert "probe failed" in entries[0].source


def test_unknown_application_is_rejected():
    with pytest.raises(KeyError, match="unknown application"):
        detect_one("notepad")


def test_a_resolved_scheme_can_be_parsed(home):
    """The point of resolving to a file: the colours can actually be shown."""
    theme = write(home / ".config/kitty/themes/mine.conf",
                  (FIXTURES / "gruvbox.kitty.conf").read_text())
    write(home / ".config/kitty/kitty.conf", "include themes/mine.conf\n")

    entry = detect_one("kitty")[0]
    palette = palette_of(entry)
    assert palette is not None
    assert palette.ansi[1].hex == "#cc241d"


def test_an_unresolved_entry_has_no_palette():
    assert palette_of(Active("vim", "editor", "gruvbox")) is None


@pytest.mark.skipif(not shutil.which("nvim"), reason="neovim not installed")
def test_neovim_is_asked_directly():
    entry = detect_one("neovim")[0]
    assert entry.source == "asked nvim"
