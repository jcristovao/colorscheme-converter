"""Round-trip properties: emit a palette, read it back, lose nothing but what
the target format genuinely cannot hold — and invent nothing at all."""

from pathlib import Path

import pytest

from cscx import parse_file
from cscx.emitters import EMITTERS, get_emitter
from cscx.fill import fill
from cscx.formats import detect_format

FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = sorted(p.name for p in FIXTURES.iterdir())
TARGETS = sorted(EMITTERS)

# Optional fields, and which formats can actually express each one. Anything
# not listed for a format must come back `None` after a round trip: a format
# that cannot store a value must not fabricate one either.
CAPABILITIES = {
    "kitty": {"cursor", "cursor_text", "selection_background",
              "selection_foreground", "indexed"},
    "ghostty": {"cursor", "cursor_text", "selection_background",
                "selection_foreground", "indexed"},
    "alacritty": {"cursor", "cursor_text", "selection_background",
                  "selection_foreground", "indexed", "dim",
                  "dim_foreground", "bright_foreground"},
    "konsole": {"dim", "dim_foreground", "bright_foreground"},
    "iterm2": {"cursor", "cursor_text", "selection_background",
               "selection_foreground"},
    "foot": {"cursor", "cursor_text", "selection_background",
             "selection_foreground", "indexed", "dim"},
    "wezterm": {"cursor", "cursor_text", "selection_background",
                "selection_foreground", "indexed"},
    # Windows Terminal has no under-cursor or selection-foreground key.
    "windows-terminal": {"cursor", "selection_background"},
    # X resources has a cursor color but no under-cursor foreground.
    "xresources": {"cursor", "selection_background", "selection_foreground",
                   "indexed"},
}

SCALAR_FIELDS = (
    "cursor", "cursor_text", "selection_background", "selection_foreground",
    "dim_foreground", "bright_foreground",
)


def round_trip(palette, target, tmp_path, derived=None):
    """Emit `palette` as `target`, write it out, and parse it back."""
    emitter = get_emitter(target)
    rendered = emitter.emit(palette, derived)
    path = tmp_path / f"out.{target}{emitter.EXTENSION}"
    if emitter.BINARY:
        path.write_bytes(rendered)
    else:
        path.write_text(rendered)
    return parse_file(path, format=target), path


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("source", SOURCES)
def test_ansi_slots_survive_every_conversion(source, target, tmp_path):
    """The 16 ANSI slots are the one thing every format can hold."""
    original = parse_file(FIXTURES / source)
    reparsed, _ = round_trip(original, target, tmp_path)
    assert reparsed.ansi == original.ansi


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("source", SOURCES)
def test_foreground_and_background_survive(source, target, tmp_path):
    original = parse_file(FIXTURES / source)
    reparsed, _ = round_trip(original, target, tmp_path)
    assert reparsed.background == original.background
    assert reparsed.foreground == original.foreground


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("source", SOURCES)
def test_optional_fields_survive_or_vanish_but_never_change(source, target, tmp_path):
    original = parse_file(FIXTURES / source)
    reparsed, _ = round_trip(original, target, tmp_path)
    supported = CAPABILITIES[target]

    for field in SCALAR_FIELDS:
        got, want = getattr(reparsed, field), getattr(original, field)

        # foot writes the cursor as `color=<text> <cursor>` and has no way to
        # set one half alone, so a source with only `cursor` loses it.
        if target == "foot" and field in {"cursor", "cursor_text"}:
            if original.cursor is None or original.cursor_text is None:
                assert got is None, "foot emitted half a cursor"
                continue

        if field in supported:
            assert got == want, f"{target} lost or altered {field}"
        else:
            assert got is None, f"{target} cannot store {field} but produced one"


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("source", SOURCES)
def test_indexed_and_dim_follow_the_same_rule(source, target, tmp_path):
    original = parse_file(FIXTURES / source)
    reparsed, _ = round_trip(original, target, tmp_path)
    supported = CAPABILITIES[target]

    if "indexed" in supported:
        assert reparsed.indexed == original.indexed
    else:
        assert reparsed.indexed == {}

    if "dim" in supported:
        assert reparsed.dim == original.dim
    else:
        assert all(c is None for c in reparsed.dim)


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("source", SOURCES)
def test_output_is_detected_as_its_own_format(source, target, tmp_path):
    """A file we wrote must sniff back as the format we wrote it in."""
    original = parse_file(FIXTURES / source)
    _, path = round_trip(original, target, tmp_path)
    ranked = detect_format(path.read_bytes(), path.name)
    assert ranked, f"{target} output matched no format"
    assert ranked[0][0] == target, f"{target} output detected as {ranked[:2]}"


@pytest.mark.parametrize("target", TARGETS)
def test_a_second_round_trip_changes_nothing(target, tmp_path):
    """Converting twice must be identical to converting once."""
    original = parse_file(FIXTURES / "gruvbox.kitty.conf")
    once, _ = round_trip(original, target, tmp_path)
    twice, _ = round_trip(once, target, tmp_path)
    assert twice.to_dict() == once.to_dict()


# -- fill -----------------------------------------------------------------

def test_fill_derives_only_what_is_missing():
    original = parse_file(FIXTURES / "gruvbox.colorscheme")  # no cursor/selection
    filled, derived = fill(original)

    assert set(derived) == {
        "cursor", "cursor_text", "selection_background", "selection_foreground",
    }
    assert filled.cursor == original.foreground
    assert filled.cursor_text == original.background
    # Inverse video: selection swaps foreground and background.
    assert filled.selection_background == original.foreground
    assert filled.selection_foreground == original.background


def test_fill_never_overwrites_a_stated_value():
    """Filling may add fields, but must never alter one the source stated."""
    original = parse_file(FIXTURES / "gruvbox.kitty.conf")
    filled, derived = fill(original)

    for field in ("background", "foreground", "cursor", "cursor_text",
                  "selection_background", "selection_foreground"):
        assert getattr(filled, field) == getattr(original, field)
        assert field not in derived
    assert filled.ansi == original.ansi
    assert filled.indexed == original.indexed

    # kitty has no intense/faint foreground, so only those two are derived.
    assert set(derived) == {"bright_foreground", "dim_foreground"}


def test_fill_recovers_foreground_and_background_from_ansi_slots(tmp_path):
    source = tmp_path / "bare.conf"
    source.write_text("\n".join(f"color{i} #{i:02x}{i:02x}{i:02x}" for i in range(16)))
    palette = parse_file(source, format="kitty")
    assert palette.background is None

    filled, derived = fill(palette)
    assert filled.background == palette.ansi[0]
    assert filled.foreground == palette.ansi[7]
    assert derived["background"] == "color0"


def test_fill_repeats_normal_colors_into_missing_bright_slots(tmp_path):
    source = tmp_path / "half.conf"
    source.write_text("\n".join(f"color{i} #{i:02x}{i:02x}{i:02x}" for i in range(8)))
    palette = parse_file(source, format="kitty")
    assert palette.ansi[8] is None

    filled, derived = fill(palette)
    assert filled.ansi[8:] == filled.ansi[:8]
    assert derived["color9"] == "color1"


def test_derived_values_are_marked_in_text_output():
    palette = parse_file(FIXTURES / "gruvbox.colorscheme")
    filled, derived = fill(palette)
    rendered = get_emitter("kitty").emit(filled, derived)
    assert "cursor               #ebdbb2  # derived: foreground" in rendered
    # Values the source really stated carry no derived marker.
    assert "#282828  # derived" not in rendered.split("color0")[0].split("cursor_text")[0]


def test_unfilled_output_omits_what_the_source_lacked():
    palette = parse_file(FIXTURES / "gruvbox.colorscheme")
    rendered = get_emitter("kitty").emit(palette)
    assert "cursor" not in rendered
    assert "selection" not in rendered


# -- structural -----------------------------------------------------------

def test_wezterm_refuses_to_pad_an_incomplete_array(tmp_path):
    """wezterm's `ansi` is fixed-length, so a partial group must be omitted."""
    source = tmp_path / "partial.conf"
    source.write_text("color0 #111111\ncolor1 #222222\nbackground #000000\n")
    palette = parse_file(source, format="kitty")
    rendered = get_emitter("wezterm").emit(palette)
    assert "ansi = [" not in rendered
    assert "# ansi omitted" in rendered
    assert "missing color2" in rendered


def test_unknown_target_is_rejected():
    with pytest.raises(KeyError, match="unknown output format"):
        get_emitter("nope")


def test_every_emitter_exposes_the_protocol():
    from cscx.emitters import _MODULES

    for module in _MODULES:
        assert isinstance(module.NAME, str) and module.NAME
        assert isinstance(module.EXTENSION, str)
        assert isinstance(module.BINARY, bool)
        assert callable(module.emit)


def test_emitters_and_parsers_cover_the_same_formats():
    """Every terminal format round-trips, and only the read-only ones do not.

    KDE is parsed but never emitted as a *terminal* format -- it is written
    through `desktops/` instead -- so it is named here rather than allowed to
    widen the rule by accident.
    """
    from cscx.formats import READ_ONLY, _MODULES as parser_modules

    assert {m.NAME for m in parser_modules} - READ_ONLY == set(EMITTERS)
    assert READ_ONLY <= {m.NAME for m in parser_modules}
    assert not READ_ONLY & set(EMITTERS)


def test_a_hostile_scheme_name_survives_every_terminal_format(tmp_path):
    """A quote or newline in the name must not corrupt the generated file."""
    original = parse_file(FIXTURES / "gruvbox.kitty.conf")
    original.name = 'evil" name\nwith \\ backslash'

    for target in TARGETS:
        reparsed, _ = round_trip(original, target, tmp_path)
        assert reparsed.ansi == original.ansi, f"{target} corrupted by the name"
