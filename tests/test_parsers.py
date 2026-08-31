"""One palette, written in every supported format, must parse identically."""

from pathlib import Path

import pytest

from cscx import parse_file
from cscx.formats import detect_format, get_parser

FIXTURES = Path(__file__).parent / "fixtures"

# The reference scheme every fixture encodes. All 16 slots differ, so an
# off-by-eight in a bright/normal mapping cannot pass unnoticed.
ANSI = [
    "#282828", "#cc241d", "#98971a", "#d79921",
    "#458588", "#b16286", "#689d6a", "#a89984",
    "#928374", "#fb4934", "#b8bb26", "#fabd2f",
    "#83a598", "#d3869b", "#8ec07c", "#ebdbb2",
]
BACKGROUND, FOREGROUND = "#282828", "#ebdbb2"
SELECTION_BG, SELECTION_FG = "#504945", "#ebdbb2"

# fixture -> (expected format, features the format can actually express)
CASES = {
    "gruvbox.kitty.conf": ("kitty", {"cursor", "cursor_text", "selection", "selection_fg", "indexed"}),
    "gruvbox.ghostty": ("ghostty", {"cursor", "cursor_text", "selection", "selection_fg"}),
    "gruvbox.alacritty.toml": ("alacritty", {"cursor", "cursor_text", "selection", "selection_fg", "indexed"}),
    "gruvbox.alacritty.yml": ("alacritty", {"cursor", "cursor_text", "selection", "selection_fg", "indexed"}),
    "gruvbox.colorscheme": ("konsole", set()),
    "gruvbox.itermcolors": ("iterm2", {"cursor", "cursor_text", "selection", "selection_fg"}),
    "gruvbox.foot.ini": ("foot", {"cursor", "cursor_text", "selection", "selection_fg", "indexed"}),
    "gruvbox.wezterm.toml": ("wezterm", {"cursor", "cursor_text", "selection", "selection_fg"}),
    # Windows Terminal has no selection-foreground key.
    "gruvbox.wt.json": ("windows-terminal", {"selection"}),
    # X resources sets a cursor color but has no under-cursor foreground.
    "gruvbox.Xresources": ("xresources", {"cursor", "selection", "selection_fg"}),
}


@pytest.mark.parametrize("filename", sorted(CASES))
def test_detected_as_the_right_format(filename):
    path = FIXTURES / filename
    ranked = detect_format(path.read_bytes(), path.name)
    assert ranked, f"{filename} matched no format"
    assert ranked[0][0] == CASES[filename][0]


@pytest.mark.parametrize("filename", sorted(CASES))
def test_ansi_slots_agree_across_formats(filename):
    palette = parse_file(FIXTURES / filename)
    assert [c.hex if c else None for c in palette.ansi] == ANSI


@pytest.mark.parametrize("filename", sorted(CASES))
def test_foreground_and_background_agree(filename):
    palette = parse_file(FIXTURES / filename)
    assert palette.background.hex == BACKGROUND
    assert palette.foreground.hex == FOREGROUND
    assert palette.is_complete


@pytest.mark.parametrize("filename", sorted(CASES))
def test_optional_features_where_the_format_has_them(filename):
    expected_format, features = CASES[filename]
    palette = parse_file(FIXTURES / filename)
    assert palette.source_format == expected_format

    if "cursor" in features:
        assert palette.cursor.hex == FOREGROUND
    if "cursor_text" in features:
        assert palette.cursor_text.hex == BACKGROUND
    if "selection" in features:
        assert palette.selection_background.hex == SELECTION_BG
    if "selection_fg" in features:
        assert palette.selection_foreground.hex == SELECTION_FG
    if "indexed" in features:
        assert palette.indexed[16].hex == "#ff8700"


@pytest.mark.parametrize("filename", sorted(CASES))
def test_explicit_format_matches_detection(filename):
    """Naming the format must give the same result as sniffing it."""
    path = FIXTURES / filename
    assert parse_file(path).to_dict() == parse_file(path, format=CASES[filename][0]).to_dict()


# -- format-specific behaviour -------------------------------------------

def test_kitty_resolves_symbolic_references():
    """`cursor_text_color background` must resolve to the background color."""
    palette = parse_file(FIXTURES / "gruvbox.kitty.conf")
    assert palette.cursor_text.hex == BACKGROUND


def test_kitty_keeps_unmapped_colors_in_extras():
    palette = parse_file(FIXTURES / "gruvbox.kitty.conf")
    assert palette.extras["kitty"]["url_color"] == "#83a598"


def test_konsole_reads_faint_slots_and_description():
    palette = parse_file(FIXTURES / "gruvbox.colorscheme")
    assert palette.name == "Gruvbox"
    assert all(c is not None for c in palette.dim)


def test_ghostty_records_background_opacity():
    palette = parse_file(FIXTURES / "gruvbox.ghostty")
    assert palette.extras["ghostty"]["background-opacity"] == 0.95


def test_foot_reads_alpha_and_two_value_cursor():
    palette = parse_file(FIXTURES / "gruvbox.foot.ini")
    assert palette.extras["foot"]["alpha"] == 0.95
    # foot writes `color=<text> <cursor>`, in that order.
    assert palette.cursor_text.hex == BACKGROUND
    assert palette.cursor.hex == FOREGROUND


def test_windows_terminal_maps_purple_to_magenta():
    palette = parse_file(FIXTURES / "gruvbox.wt.json")
    assert palette.ansi[5].hex == ANSI[5]
    assert palette.ansi[13].hex == ANSI[13]


def test_windows_terminal_finds_scheme_inside_settings_json(tmp_path):
    settings = tmp_path / "settings.json"
    source = (FIXTURES / "gruvbox.wt.json").read_text()
    settings.write_text('{"profiles": {}, "schemes": [' + source + "]}")
    palette = parse_file(settings)
    assert [c.hex for c in palette.ansi] == ANSI


def test_wezterm_takes_its_name_from_metadata():
    palette = parse_file(FIXTURES / "gruvbox.wezterm.toml")
    assert palette.name == "Gruvbox"


def test_iterm2_reads_float_components_without_rounding_drift():
    palette = parse_file(FIXTURES / "gruvbox.itermcolors")
    assert [c.hex for c in palette.ansi] == ANSI


# -- robustness ----------------------------------------------------------

def test_missing_values_are_reported_not_invented(tmp_path):
    partial = tmp_path / "partial.conf"
    partial.write_text("background #282828\ncolor0 #282828\ncolor1 #cc241d\n")
    palette = parse_file(partial, format="kitty")
    assert not palette.is_complete
    assert "foreground" in palette.missing()
    assert palette.ansi[2] is None


def test_unreadable_color_does_not_lose_the_rest_of_the_file(tmp_path):
    broken = tmp_path / "broken.conf"
    broken.write_text("color0 #282828\ncolor1 notacolor\ncolor2 #98971a\n")
    palette = parse_file(broken, format="kitty")
    assert palette.ansi[0].hex == "#282828"
    assert palette.ansi[1] is None
    assert palette.ansi[2].hex == "#98971a"


def test_unknown_format_name_is_rejected():
    with pytest.raises(KeyError, match="unknown format"):
        get_parser("nope")


def test_every_registered_parser_exposes_the_protocol():
    from cscx.formats import _MODULES

    for module in _MODULES:
        assert isinstance(module.NAME, str) and module.NAME
        assert isinstance(module.BINARY, bool)
        assert callable(module.detect) and callable(module.parse)
        # A sniffer must return a usable score for empty input, not explode.
        assert 0.0 <= module.detect(b"" if module.BINARY else "", None) <= 1.0
