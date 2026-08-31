import pytest

from cscx.color import Color, ColorParseError, parse_color


@pytest.mark.parametrize(
    "text,expected",
    [
        ("#282828", "#282828"),
        ("282828", "#282828"),
        ("0x282828", "#282828"),
        ("0X282828", "#282828"),
        ("#fff", "#ffffff"),
        ("#abc", "#aabbcc"),
        ("rgb:28/28/28", "#282828"),
        ("rgb:f/f/f", "#ffffff"),          # 1-digit components scale up
        ("rgb:ffff/0000/0000", "#ff0000"),  # 4-digit components scale down
        ("rgb(40, 40, 40)", "#282828"),
        ("rgba(40, 40, 40, 0.5)", "#282828"),
        ("40,40,40", "#282828"),
        ("235,219,178", "#ebdbb2"),
        ("cornflowerblue", "#6495ed"),
        ("Black", "#000000"),
        ("  '#282828'  ", "#282828"),      # quoted and padded
        ('"#282828"', "#282828"),
    ],
)
def test_parses_every_spelling(text, expected):
    assert parse_color(text).hex == expected


def test_alpha_is_read_but_optional():
    assert parse_color("#282828").a is None
    assert parse_color("#28282880").a == pytest.approx(0.502, abs=1e-3)
    assert parse_color("rgba(0,0,0,0.25)").a == pytest.approx(0.25)


def test_none_and_empty_pass_through():
    assert parse_color(None) is None
    assert parse_color("") is None
    assert parse_color("   ") is None


@pytest.mark.parametrize("text", ["nonsense", "#gg0000", "#12", "rgb:zz/00/00", "999,0,0"])
def test_rejects_junk(text):
    with pytest.raises(ColorParseError):
        parse_color(text)


def test_from_floats_matches_iterm2_components():
    assert Color.from_floats(0.156862, 0.156862, 0.156862).hex == "#282828"
    assert Color.from_floats(1.0, 1.0, 1.0).hex == "#ffffff"


def test_render_forms():
    color = Color(235, 219, 178)
    assert color.hex == "#ebdbb2"
    assert color.hex_bare == "ebdbb2"
    assert color.rgb_triple == "235,219,178"
    assert str(color) == "#ebdbb2"


def test_channels_are_validated():
    with pytest.raises(ColorParseError):
        Color(256, 0, 0)
    with pytest.raises(ColorParseError):
        Color(0, 0, 0, a=1.5)
