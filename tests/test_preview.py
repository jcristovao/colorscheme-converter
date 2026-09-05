"""The preview renderer: ANSI output the eye can judge."""

import re
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.preview import RESET, render, swatch_strip
from cscx.preview import _visible_length as visible_length

FIXTURES = Path(__file__).parent / "fixtures"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


def test_render_emits_truecolour_escapes(gruvbox):
    output = render(gruvbox)
    assert "\x1b[48;2;40;40;40m" in output      # the background
    assert "\x1b[38;2;235;219;178m" in output   # the foreground


def test_every_panel_row_is_the_requested_width(gruvbox):
    """Ragged rows would read as a broken window rather than a terminal."""
    for width in (60, 76, 100):
        rows = [
            line for line in render(gruvbox, width=width).splitlines()
            if line.startswith("\x1b[48;2;40;40;40m")
        ]
        assert rows, "no panel rows rendered"
        assert {visible_length(line) for line in rows} == {width}


def test_every_escape_sequence_is_closed(gruvbox):
    output = render(gruvbox)
    for line in output.splitlines():
        if ANSI.search(line):
            assert line.endswith(RESET), line[:60]


def test_visible_length_ignores_escapes():
    assert visible_length("\x1b[1mabc\x1b[0m") == 3
    assert visible_length("plain") == 5


def test_swatch_strip_has_one_block_per_slot(gruvbox):
    assert visible_length(swatch_strip(gruvbox, width=1)) == 16
    assert visible_length(swatch_strip(gruvbox, width=2)) == 32


def test_preview_shows_the_name_and_source_format(gruvbox):
    plain = ANSI.sub("", render(gruvbox))
    assert "gruvbox" in plain
    assert "kitty" in plain


def test_preview_reports_comment_contrast(gruvbox):
    plain = ANSI.sub("", render(gruvbox))
    assert "comments" in plain and ":1 vs background" in plain


def test_an_incomplete_palette_still_previews(tmp_path):
    """Filling covers the syntax sample; the palette strip needs nothing."""
    source = tmp_path / "partial.conf"
    source.write_text("\n".join(f"color{i} #{i * 17:02x}0000" for i in range(8)))
    plain = ANSI.sub("", render(parse_file(source, format="kitty")))
    assert "def contrast" in plain


def test_a_missing_hue_degrades_to_a_note_instead_of_failing(tmp_path):
    source = tmp_path / "nohue.conf"
    source.write_text(
        "\n".join(f"color{i} #{i * 17:02x}0000" for i in range(8) if i != 3)
    )
    plain = ANSI.sub("", render(parse_file(source, format="kitty")))
    assert "no syntax preview" in plain
    assert "color3" in plain


def test_terminal_sample_survives_a_palette_with_no_selection():
    """konsole stores no selection colour; the sample must still draw."""
    palette = parse_file(FIXTURES / "gruvbox.colorscheme")
    assert palette.selection_background is None
    assert "selected text" in ANSI.sub("", render(palette))


def test_the_panels_have_a_straight_right_edge():
    """Padding must be painted inside the panel, not after it.

    Every painted run ends with a reset, so a line built as
    `background + body + padding + reset` leaves its trailing spaces
    unstyled -- and the panel frays on any terminal whose own background
    differs from the scheme's, which is the whole point of previewing it.
    """
    import re

    from cscx import parse_file
    from cscx.preview import render

    output = render(parse_file(FIXTURES / "gruvbox.kitty.conf"))
    for line in output.split("\n"):
        assert not re.search(r"\x1b\[0m +\x1b\[0m$", line), repr(line)
