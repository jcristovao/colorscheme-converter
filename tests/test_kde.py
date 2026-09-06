"""The KDE desktop writer, and the reader that keeps it honest.

The round trip is the same contract every other target is held to: emit a
palette, read it back, and assert that nothing was lost and nothing was
invented. The other half of this file checks the judgement calls, and the
sharpest test in it is `test_breeze_passes_its_own_gates` -- a contrast gate
that fires on the scheme KDE itself ships is noise, not a finding.
"""

import configparser
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.color import Color, contrast_ratio, luminance, parse_color
from cscx.desktops import DESKTOPS, get_desktop, scheme_warnings
from cscx.desktops import kde as kde_desktop
from cscx.editors import EditorPaletteError
from cscx.formats import detect_format
from cscx.mapping import DEFAULT, MappingError, _merge

FIXTURES = Path(__file__).parent / "fixtures"
SYSTEM_SCHEMES = Path("/usr/share/color-schemes")

#: A palette written in a `.colors` file *verbatim*, and therefore the only
#: thing a round trip can be asked about.
ROUND_TRIPPED = ("background", "foreground", 1, 2, 3, 4, 5, 6)


def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


def emit(palette=None, **kwargs):
    return get_desktop("kde").emit(palette or gruvbox(), **kwargs)


def sections(text):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(text)
    return parser


# -- structure ------------------------------------------------------------


def test_every_colour_set_is_written_in_full():
    """A missing key falls back to a hardcoded Breeze *Light* constant.

    Which is how a dark scheme ends up with a blinding white tooltip, so the
    file has to be complete rather than minimal.
    """
    parsed = sections(emit())
    for name in kde_desktop.SETS:
        assert parsed.has_section(name), f"{name} missing"
        assert set(parsed[name]) == set(kde_desktop.KEYS), f"{name} is incomplete"


def test_the_structure_matches_a_scheme_plasma_ships():
    """Same sections and same keys as Breeze, which is the reference."""
    breeze = SYSTEM_SCHEMES / "BreezeDark.colors"
    if not breeze.is_file():
        pytest.skip("no system colour schemes installed")

    ours, theirs = sections(emit()), sections(breeze.read_text())
    for name in kde_desktop.SETS:
        assert set(ours[name]) == set(theirs[name]), f"{name} keys differ from Breeze"

    for section in ("General", "KDE", "WM", "ColorEffects:Disabled",
                    "ColorEffects:Inactive"):
        assert ours.has_section(section)
    assert set(ours["WM"]) <= set(theirs["WM"])


def test_values_are_decimal_triples():
    """KConfig canonicalises to `r,g,b`; anything else is a needless dialect."""
    parsed = sections(emit())
    for name in kde_desktop.SETS:
        for key, value in parsed[name].items():
            channels = value.split(",")
            assert len(channels) == 3, f"{name}/{key} = {value!r}"
            assert all(c.isdigit() and 0 <= int(c) <= 255 for c in channels)


def test_the_scheme_id_matches_the_filename_it_installs_as():
    """Plasma finds a scheme by its file stem, so the two cannot disagree."""
    palette = gruvbox()
    palette.name = "My Scheme"
    parsed = sections(emit(palette))

    stem = get_desktop("kde").FILENAME.format(name="my-scheme")
    assert parsed["General"]["ColorScheme"] == Path(stem).stem
    assert parsed["General"]["Name"] == "My Scheme"


def test_the_window_manager_section_agrees_with_the_header_set():
    """KWin prefers Colors:Header and falls back to [WM]; both are written."""
    parsed = sections(emit())
    assert parsed["WM"]["activeBackground"] == \
        parsed["Colors:Header"]["BackgroundNormal"]
    assert parsed["WM"]["activeForeground"] == \
        parsed["Colors:Header"]["ForegroundNormal"]
    assert parsed["WM"]["inactiveBackground"] == \
        parsed["Colors:Header][Inactive"]["BackgroundNormal"]


def test_a_hostile_scheme_name_cannot_break_out_of_the_file():
    palette = gruvbox()
    palette.name = 'evil\nColorScheme=hijacked\n[Colors:View]\nBackgroundNormal=255,0,0'

    parsed = sections(emit(palette))
    assert parsed["General"]["ColorScheme"] != "hijacked"
    assert "\n" not in parsed["General"]["Name"]
    assert parsed["Colors:View"]["BackgroundNormal"] == gruvbox().background.rgb_triple


# -- the round trip -------------------------------------------------------


def test_round_trip_keeps_what_kde_holds_and_invents_nothing(tmp_path):
    original = gruvbox()
    path = tmp_path / "out.colors"
    path.write_text(emit(original))
    back = parse_file(path)

    assert back.source_format == "kde"
    assert back.background == original.background
    assert back.foreground == original.foreground

    for slot in range(16):
        expected = original.ansi[slot] if slot in ROUND_TRIPPED else None
        assert back.ansi[slot] == expected, f"color{slot}"

    # Ten of sixteen slots, the cursor, the selection and dim have no home in
    # a .colors file. Losing them is correct; producing them would not be.
    for field in ("cursor", "cursor_text", "selection_background",
                  "selection_foreground", "dim_foreground", "bright_foreground"):
        assert getattr(back, field) is None, f"kde cannot store {field}"
    assert back.indexed == {}
    assert all(color is None for color in back.dim)


def test_a_kde_scheme_cannot_be_re_emitted_as_one(tmp_path):
    """The asymmetry, stated as a test rather than left to be discovered.

    Every terminal format converts twice to the same result. KDE cannot: it
    holds six hues, and writing a scheme needs all eight. Refusing is the
    honest answer -- the alternative is inventing the two it never had.
    """
    path = tmp_path / "one.colors"
    path.write_text(emit())

    with pytest.raises(EditorPaletteError, match="color0, color7"):
        emit(parse_file(path))


def test_the_accent_is_deliberately_not_read_back(tmp_path):
    """ForegroundActive and DecorationFocus hold the accent, not an ANSI slot.

    Reading them would invent a hue the source never stated, which is the one
    thing every parser in this package is forbidden to do.
    """
    path = tmp_path / "out.colors"
    path.write_text(emit())
    parsed = sections(path.read_text())

    accent = parsed["Colors:View"]["ForegroundActive"]
    assert parsed["Colors:View"]["DecorationFocus"] == accent
    assert accent not in {
        color.rgb_triple for color in parse_file(path).ansi if color is not None
    }


# -- detection ------------------------------------------------------------


def test_output_is_detected_as_kde(tmp_path):
    path = tmp_path / "out.colors"
    path.write_text(emit())
    ranked = detect_format(path.read_bytes(), path.name)
    assert ranked and ranked[0][0] == "kde"


def test_gimp_palettes_sharing_the_extension_are_not_claimed():
    """/etc/xdg/colors/*.colors are GIMP palettes for KDE's colour picker."""
    gimp = b"GIMP Palette\nName: Web\nColumns: 0\n#\n  0   0   0\tBlack\n"
    assert not [name for name, _ in detect_format(gimp, "Web.colors")]


def test_konsole_schemes_are_not_claimed():
    data = (FIXTURES / "gruvbox.colorscheme").read_bytes()
    ranked = detect_format(data, "gruvbox.colorscheme")
    assert ranked[0][0] == "konsole"
    assert "kde" not in dict(ranked)


@pytest.mark.skipif(not SYSTEM_SCHEMES.is_dir(), reason="no system colour schemes")
def test_installed_schemes_are_read():
    breeze = SYSTEM_SCHEMES / "BreezeDark.colors"
    if not breeze.is_file():
        pytest.skip("BreezeDark not installed")

    palette = parse_file(breeze)
    assert palette.name == "Breeze Dark"
    assert palette.background.hex == "#141618"
    # The six hues KDE holds, and only those.
    stated = [i for i, color in enumerate(palette.ansi) if color is not None]
    assert stated == [1, 2, 3, 4, 5, 6]


# -- the gates ------------------------------------------------------------


def _breeze_scheme(path):
    """A `Scheme` holding Breeze's own colours, so the gates can judge them."""
    parsed = sections(path.read_text())
    scheme = kde_desktop.Scheme()
    for name in kde_desktop.SETS:
        scheme.sets[name] = {
            key: parse_color(parsed[name][key]) for key in kde_desktop.KEYS
        }
    scheme.dark = luminance(scheme.sets["Colors:View"]["BackgroundNormal"]) < 0.5
    return scheme


@pytest.mark.parametrize("name", ["BreezeDark", "BreezeLight"])
def test_breeze_passes_its_own_gates(name):
    """The calibration test.

    Every bar in `_validate` is set where it is because the scheme KDE ships
    clears it. A gate Breeze fails would fire on almost everything cscx
    generates, and a warning that always fires teaches nobody anything.
    """
    path = SYSTEM_SCHEMES / f"{name}.colors"
    if not path.is_file():
        pytest.skip(f"{name} not installed")

    scheme = _breeze_scheme(path)
    background = scheme.sets["Colors:View"]["BackgroundNormal"]
    found = kde_desktop._validate(scheme, background)

    # Breeze Light is the one exception, and it is a real finding rather than
    # a miscalibrated gate: its accent blue is mid-luminance and its surfaces
    # are near white, so its focus ring lands at 1.9:1 on its own header. That
    # is a long-standing KDE accessibility complaint. It is also the only gate
    # cscx *fixes* rather than merely reports -- the accent is moved until a
    # ring in it clears 3:1 on every surface -- so cscx's own output never
    # trips it. Every other bar here is set where Breeze clears it.
    assert [warning for warning in found if not warning.startswith("focus rings")] == []


def test_a_low_contrast_source_is_reported_once_per_problem_not_per_set(tmp_path):
    """Seven near-identical lines for one cause is noise, not seven findings."""
    source = tmp_path / "washed.conf"
    source.write_text(
        "background #808080\nforeground #8a8a8a\n"
        + "\n".join(f"color{i} #{i * 16:02x}8080" for i in range(16))
    )
    palette = parse_file(source, format="kitty")
    found = scheme_warnings(palette)

    assert found, "an unreadable scheme must say so"
    assert len(found) == len(set(found))
    assert sum(warning.startswith("normal text:") for warning in found) == 1
    assert sum(warning.startswith("secondary text") for warning in found) == 1


def test_a_pure_black_background_keeps_its_surfaces_apart():
    """Plasma stops shading below luma 0.006, taking every frame with it.

    Lifting each surface separately would pile them all onto the floor, so the
    ramp's base is lifted instead and the spacing survives.
    """
    palette = parse_file(FIXTURES / "gruvbox.kitty.conf")
    palette.background = Color(0, 0, 0)
    parsed = sections(emit(palette))

    view = parsed["Colors:View"]["BackgroundNormal"]
    surfaces = [
        parse_color(parsed[name]["BackgroundNormal"])
        for name in ("Colors:Window", "Colors:Button", "Colors:Header")
    ]
    assert view == "0,0,0", "the stated background must survive untouched"
    assert all(luminance(c) >= kde_desktop.SHADE_FLOOR for c in surfaces)
    assert len({c.hex for c in surfaces}) > 1, "surfaces collapsed onto each other"

    assert any("too dark for Plasma to shade" in w for w in scheme_warnings(palette))


# -- the accent -----------------------------------------------------------


def test_a_selection_too_close_to_the_chrome_is_not_used_as_the_accent():
    """Terminals draw text *on* the selection, so it sits near the background.

    Gruvbox's is #504945 against its own #282828: invisible as a focus ring.
    """
    parsed = sections(emit())
    accent = parse_color(parsed["Colors:View"]["DecorationFocus"])
    assert accent != gruvbox().selection_background

    for name in kde_desktop.SETS:
        if name == "Colors:Selection":
            continue  # Breeze sets focus equal to the highlight here too
        surface = parse_color(parsed[name]["BackgroundNormal"])
        assert contrast_ratio(accent, surface) >= kde_desktop.DIM_CONTRAST


def test_a_selection_that_can_carry_a_focus_ring_is_used(tmp_path):
    palette = gruvbox()
    palette.selection_background = Color(0xE0, 0x60, 0xC0)
    parsed = sections(emit(palette))
    assert parsed["Colors:View"]["DecorationFocus"] == "224,96,192"


def test_cyan_reaches_the_desktop_as_the_hover_decoration():
    """The one hue with no semantic foreground of its own."""
    parsed = sections(emit())
    assert parsed["Colors:View"]["DecorationHover"] == gruvbox().ansi[6].rgb_triple


def test_the_semantic_hues_are_written_verbatim():
    parsed = sections(emit())["Colors:View"]
    palette = gruvbox()
    assert parsed["ForegroundNegative"] == palette.ansi[1].rgb_triple
    assert parsed["ForegroundPositive"] == palette.ansi[2].rgb_triple
    assert parsed["ForegroundNeutral"] == palette.ansi[3].rgb_triple
    assert parsed["ForegroundLink"] == palette.ansi[4].rgb_triple
    assert parsed["ForegroundVisited"] == palette.ansi[5].rgb_triple


def test_the_semantic_hues_are_moved_clear_of_the_highlight():
    """The accent is usually ANSI 4, and ForegroundLink *is* ANSI 4.

    Carried over unchanged, a link on the selection is drawn in its own
    background colour: 1.0:1, and perfectly invisible. Breeze shifts four of
    its hues by hand for the same reason.
    """
    parsed = sections(emit())
    selection = parsed["Colors:Selection"]
    background = parse_color(selection["BackgroundNormal"])

    for key in kde_desktop._SELECTION_HUES:
        ratio = contrast_ratio(parse_color(selection[key]), background)
        assert ratio >= kde_desktop.SELECTION_HUE_CONTRAST, f"{key} at {ratio:.2f}:1"

    # The specific regression: the link must not be the highlight itself.
    assert selection["ForegroundLink"] != selection["BackgroundNormal"]
    # ... and it must still be recognisably the scheme's own hue, not a swap.
    assert selection["ForegroundLink"] != parsed["Colors:View"]["ForegroundLink"]


def test_the_surface_sets_keep_their_hues_unshifted():
    """Only the highlight needs the adjustment; everywhere else is verbatim."""
    parsed = sections(emit())
    palette = gruvbox()
    for name in kde_desktop.SETS:
        if name in {"Colors:Selection", "Colors:Complementary"}:
            continue
        assert parsed[name]["ForegroundLink"] == palette.ansi[4].rgb_triple, name


# -- light schemes --------------------------------------------------------


def light_palette(tmp_path):
    source = tmp_path / "light.conf"
    source.write_text(
        "background #fdf6e3\nforeground #586e75\n"
        "color0 #073642\ncolor1 #dc322f\ncolor2 #859900\ncolor3 #b58900\n"
        "color4 #268bd2\ncolor5 #d33682\ncolor6 #2aa198\ncolor7 #eee8d5\n"
        "color8 #002b36\ncolor9 #cb4b16\ncolor10 #586e75\ncolor11 #657b83\n"
        "color12 #839496\ncolor13 #6c71c4\ncolor14 #93a1a1\ncolor15 #fdf6e3\n"
    )
    return parse_file(source, format="kitty")


def test_a_light_scheme_inverts_the_complementary_set(tmp_path):
    """Plasma uses it for lock and logout screens; both Breeze schemes are dark."""
    palette = light_palette(tmp_path)
    parsed = sections(emit(palette))

    complementary = parse_color(parsed["Colors:Complementary"]["BackgroundNormal"])
    view = parse_color(parsed["Colors:View"]["BackgroundNormal"])
    assert luminance(complementary) < luminance(view)
    # The darkest colour the scheme actually states, rather than an invention.
    assert complementary == palette.ansi[0]
    assert any("complementary set" in w for w in scheme_warnings(palette))


def test_the_inverted_set_gets_an_accent_that_works_against_it(tmp_path):
    """One fitted to light surfaces would vanish on a dark one."""
    parsed = sections(emit(light_palette(tmp_path)))
    section = parsed["Colors:Complementary"]
    assert contrast_ratio(
        parse_color(section["DecorationFocus"]),
        parse_color(section["BackgroundNormal"]),
    ) >= kde_desktop.DIM_CONTRAST


def test_a_light_scheme_steps_its_surfaces_away_from_the_background(tmp_path):
    """Breeze Light floats content above its chrome; the ramp must follow."""
    parsed = sections(emit(light_palette(tmp_path)))
    view = luminance(parse_color(parsed["Colors:View"]["BackgroundNormal"]))
    window = luminance(parse_color(parsed["Colors:Window"]["BackgroundNormal"]))
    header = luminance(parse_color(parsed["Colors:Header"]["BackgroundNormal"]))
    assert view > window > header


# -- the mapping ----------------------------------------------------------


def test_the_accent_can_be_pinned_to_a_slot():
    mapping = _merge(DEFAULT, {"kde": {"accent": 5, "hover": "accent"}})
    scheme = kde_desktop.resolve(gruvbox(), mapping=mapping)
    view = scheme.sets["Colors:View"]
    assert view["DecorationHover"] == view["DecorationFocus"]
    assert "color5" in dict((n, s) for n, _, s in scheme.provenance)["accent"]


def test_the_surface_ramp_can_be_widened():
    mapping = _merge(DEFAULT, {"kde": {"window": 0.30}})
    default = kde_desktop.resolve(gruvbox())
    widened = kde_desktop.resolve(gruvbox(), mapping=mapping)
    assert luminance(widened.sets["Colors:Window"]["BackgroundNormal"]) > \
        luminance(default.sets["Colors:Window"]["BackgroundNormal"])


@pytest.mark.parametrize("document, message", [
    ({"kde": {"accent": 16}}, "ANSI slot"),
    ({"kde": {"accent": "wallpaper"}}, "ANSI slot"),
    ({"kde": {"hover": True}}, "ANSI slot"),
    ({"kde": {"window": 2.0}}, "fraction"),
    ({"kde": {"window": "wide"}}, "number"),
    ({"kde": {"headers": 0.1}}, "unknown"),
])
def test_a_bad_kde_override_is_an_error_naming_the_alternatives(document, message):
    with pytest.raises(MappingError, match=message):
        _merge(DEFAULT, document)


def test_the_dumped_mapping_round_trips_through_the_reader():
    import tomllib

    from cscx.mapping import dump

    document = tomllib.loads(dump(DEFAULT))
    assert _merge(DEFAULT, document).surfaces == DEFAULT.surfaces
    assert _merge(DEFAULT, document).kde_accent == DEFAULT.kde_accent


# -- refusals -------------------------------------------------------------


def test_a_palette_missing_a_hue_is_refused_not_guessed(tmp_path):
    source = tmp_path / "partial.conf"
    source.write_text("background #000000\nforeground #ffffff\ncolor1 #ff0000\n")
    palette = parse_file(source, format="kitty")

    with pytest.raises(EditorPaletteError, match="eight normal ANSI colors"):
        emit(palette)
    # The CLI reports rather than raising, so warnings must stay quiet too.
    assert scheme_warnings(palette) == []


def test_terminal_exact_uses_palette_colours_only():
    exact = sections(emit(terminal_exact=True))["Colors:View"]
    palette = gruvbox()
    assert exact["ForegroundInactive"] == palette.ansi[7].rgb_triple


def test_activating_under_a_new_name_keeps_the_file_and_the_scheme_id_agreed(tmp_path):
    """Plasma finds a scheme by its file stem, so a rename has to reach inside.

    `--name` changes where the file goes; without this the ColorScheme key
    would still carry the palette's own name and quietly disagree with it.
    """
    from cscx.activation import plan

    proposed = plan(gruvbox(), "kde", name="Gruvbox cscx")
    step = proposed.steps[0]
    assert step.path.name == "gruvbox-cscx.colors"
    assert sections(step.content)["General"]["ColorScheme"] == "gruvbox-cscx"


def test_activating_without_a_name_keeps_the_palette_display_name():
    from cscx.activation import plan

    step = plan(gruvbox(), "kde").steps[0]
    parsed = sections(step.content)
    assert parsed["General"]["ColorScheme"] == step.path.stem
    assert parsed["General"]["Name"] == "gruvbox.kitty"


def test_activation_carries_the_schemes_caveats_into_the_plan(tmp_path):
    """--dry-run is when you would want to read them, before anything happens."""
    from cscx.activation import plan

    source = tmp_path / "washed.conf"
    source.write_text(
        "background #808080\nforeground #8a8a8a\n"
        + "\n".join(f"color{i} #{i * 16:02x}8080" for i in range(16))
    )
    palette = parse_file(source, format="kitty")

    proposed = plan(palette, "kde")
    assert proposed.warnings == scheme_warnings(palette)
    assert any("normal text" in line for line in proposed.describe().splitlines())


def test_a_clean_scheme_activates_without_noise():
    from cscx.activation import plan

    assert plan(gruvbox(), "kde").warnings == []


def test_the_registry_exposes_the_protocol():
    for name, desktop in DESKTOPS.items():
        assert desktop.NAME == name
        assert desktop.EXTENSION.startswith(".")
        assert "{name}" in desktop.FILENAME
        assert "{name}" in desktop.INSTALL_PATH
        assert desktop.BINARY is False
        assert callable(desktop.emit) and callable(desktop.warnings)


def test_an_unknown_desktop_is_rejected():
    with pytest.raises(KeyError, match="unknown desktop"):
        get_desktop("gnome")
