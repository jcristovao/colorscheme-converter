"""Reading neovim colorschemes back into palettes."""

import json
import shutil
from pathlib import Path

import pytest

from cscx.nvim_themes import (
    NvimUnavailable,
    _build,
    _safe,
    available,
    cache_dir,
    export,
    extract,
)

NORD_TERMINAL = [
    "#2E3440", "#BF616A", "#A3BE8C", "#EBCB8B", "#81A1C1", "#B48EAD",
    "#88C0D0", "#E5E9F0", "#4C566A", "#BF616A", "#A3BE8C", "#EBCB8B",
    "#81A1C1", "#B48EAD", "#8FBCBB", "#ECEFF4",
]

#: A scheme that sets no terminal_color_*, so its palette must be derived.
CATPPUCCIN = {
    "DiagnosticError": {"fg": "#f38ba8"},
    "String": {"fg": "#a6e3a1"},
    "Type": {"fg": "#f9e2af"},
    "Function": {"fg": "#89b4fa"},
    "Keyword": {"fg": "#cba6f7"},
    "Special": {"fg": "#f5c2e7"},
}


def entry(name="test", terminal=None, groups=None, background="dark"):
    base = {
        "Normal": {"fg": "#cdd6f4", "bg": "#1e1e2e"},
        "Cursor": {"fg": "#1e1e2e", "bg": "#cdd6f4"},
        "Visual": {"bg": "#45475a"},
        "CursorLine": {"bg": "#2a2b3c"},
    }
    base.update(groups or {})
    return {
        "name": name,
        "background": background,
        "terminal": terminal if terminal is not None else [None] * 16,
        "groups": base,
    }


# -- the exact path -------------------------------------------------------


def test_terminal_colours_are_taken_verbatim():
    built = _build(entry(terminal=NORD_TERMINAL))
    assert built.exact
    assert [c.hex for c in built.palette.ansi] == [c.lower() for c in NORD_TERMINAL]


def test_an_exact_palette_records_that_it_was_exact():
    built = _build(entry(name="nord", terminal=NORD_TERMINAL))
    assert built.palette.extras["neovim"] == {
        "colorscheme": "nord", "palette": "exact", "background": "dark",
    }


def test_a_partial_terminal_palette_is_not_treated_as_exact():
    """Fifteen of sixteen is not a palette; fall through to deriving."""
    partial = list(NORD_TERMINAL)
    partial[5] = None
    built = _build(entry(terminal=partial, groups=CATPPUCCIN))
    assert built is not None
    assert not built.exact
    # The derived slots are used, not the fifteen that happened to be set.
    assert built.palette.ansi[1].hex == "#f38ba8"


def test_a_partial_palette_with_nothing_to_derive_from_is_skipped():
    partial = list(NORD_TERMINAL)
    partial[5] = None
    assert _build(entry(terminal=partial)) is None


def test_cursor_and_selection_come_from_highlight_groups():
    built = _build(entry(terminal=NORD_TERMINAL))
    assert built.palette.cursor.hex == "#cdd6f4"
    assert built.palette.cursor_text.hex == "#1e1e2e"
    assert built.palette.selection_background.hex == "#45475a"


# -- the derived path -----------------------------------------------------


def test_semantic_groups_become_ansi_slots():
    """The inverse of the mapping used to write editor themes."""
    built = _build(entry(groups=CATPPUCCIN))
    assert not built.exact

    palette = built.palette
    assert palette.ansi[1].hex == "#f38ba8"      # red    <- DiagnosticError
    assert palette.ansi[2].hex == "#a6e3a1"      # green  <- String
    assert palette.ansi[3].hex == "#f9e2af"      # yellow <- Type
    assert palette.ansi[4].hex == "#89b4fa"      # blue   <- Function
    assert palette.ansi[5].hex == "#cba6f7"      # magenta<- Keyword
    assert palette.ansi[6].hex == "#f5c2e7"      # cyan   <- Special


def test_a_derived_palette_says_so():
    assert _build(entry(groups=CATPPUCCIN)).palette.extras["neovim"]["palette"] == "derived"


def test_derived_palettes_are_complete():
    palette = _build(entry(groups=CATPPUCCIN)).palette
    assert palette.is_complete
    assert palette.background.hex == "#1e1e2e"
    assert palette.foreground.hex == "#cdd6f4"


def test_bright_slots_step_toward_the_extreme():
    palette = _build(entry(groups=CATPPUCCIN)).palette
    for index in range(8):
        assert palette.ansi[index + 8] != palette.ansi[index]


def test_fallback_groups_are_tried_in_order():
    """ErrorMsg stands in when DiagnosticError is not set."""
    groups = dict(CATPPUCCIN)
    del groups["DiagnosticError"]
    groups["ErrorMsg"] = {"fg": "#ff0000"}
    assert _build(entry(groups=groups)).palette.ansi[1].hex == "#ff0000"


def test_a_scheme_with_too_little_colour_is_skipped():
    """Better no answer than a palette invented out of a monochrome theme."""
    assert _build(entry(groups={"String": {"fg": "#a6e3a1"}})) is None


def test_a_scheme_without_a_normal_background_is_skipped():
    bare = entry(groups=CATPPUCCIN)
    bare["groups"]["Normal"] = {}
    assert _build(bare) is None


# -- export ---------------------------------------------------------------


def test_export_writes_kitty_files_with_provenance(tmp_path, monkeypatch):
    import cscx.nvim_themes as module

    monkeypatch.setattr(
        module, "extract",
        lambda only=None: [_build(entry(name="nord", terminal=NORD_TERMINAL))],
    )
    written = export(tmp_path)

    assert [p.name for p in written] == ["nord.conf"]
    text = written[0].read_text()
    assert "# neovim colorscheme: nord" in text
    assert "exact (terminal_color_*)" in text
    assert any(line.startswith("color1") and "#bf616a" in line
               for line in text.splitlines())


def test_exported_files_parse_back_as_kitty(tmp_path, monkeypatch):
    """The whole point: they become browsable and convertible like anything else."""
    import cscx.nvim_themes as module
    from cscx import parse_file

    monkeypatch.setattr(
        module, "extract",
        lambda only=None: [_build(entry(name="nord", terminal=NORD_TERMINAL))],
    )
    written = export(tmp_path)
    palette = parse_file(written[0])
    assert [c.hex for c in palette.ansi] == [c.lower() for c in NORD_TERMINAL]


def test_derived_exports_are_labelled(tmp_path, monkeypatch):
    import cscx.nvim_themes as module

    monkeypatch.setattr(
        module, "extract",
        lambda only=None: [_build(entry(name="catppuccin", groups=CATPPUCCIN))],
    )
    assert "derived from highlight groups" in export(tmp_path)[0].read_text()


def test_awkward_scheme_names_become_safe_filenames():
    assert _safe("base16-atelier-cave") == "base16-atelier-cave"
    assert "/" not in _safe("a/b")
    assert " " not in _safe("a b")


def test_the_cache_lives_under_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_dir() == tmp_path / "cscx/nvim"


def test_a_missing_neovim_is_reported_clearly(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(NvimUnavailable, match="not installed"):
        available()
    with pytest.raises(NvimUnavailable, match="not installed"):
        extract()


def test_unreadable_output_is_reported(monkeypatch):
    import cscx.nvim_themes as module

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/nvim")
    monkeypatch.setattr(module, "_run", lambda command: "no json here")
    with pytest.raises(NvimUnavailable, match="nothing to read"):
        extract()


def test_malformed_json_is_reported(monkeypatch):
    import cscx.nvim_themes as module

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/nvim")
    monkeypatch.setattr(module, "_run", lambda command: "[{broken")
    with pytest.raises(NvimUnavailable, match="could not read"):
        extract()


# -- against a real neovim ------------------------------------------------


@pytest.mark.skipif(not shutil.which("nvim"), reason="neovim not installed")
def test_available_lists_colorschemes():
    names = available()
    assert "default" in names
    assert len(names) > 5


@pytest.mark.skipif(not shutil.which("nvim"), reason="neovim not installed")
def test_extracting_a_named_scheme_from_a_real_neovim():
    items = extract(only=["default", "habamax"])
    assert {item.name for item in items} <= {"default", "habamax"}
    assert items, "neovim returned no schemes"
    for item in items:
        assert item.palette.is_complete
        assert item.palette.background is not None
