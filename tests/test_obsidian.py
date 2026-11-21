"""The Obsidian writer, and the vault-aware plumbing around it.

Obsidian derives several hundred semantic variables from a dozen foundation
colours, so most of what is worth checking is that the foundations land on
the right roles -- above all that `--text-faint`, which Obsidian uses for
code comments and Markdown syntax characters, is the one shade whose contrast
is guaranteed. The rest is structural: a theme is two files in a directory
whose name must match its manifest, inside a vault nobody may guess.

Everything touching a vault runs against a sandboxed HOME.
"""

import colorsys
import json
import re
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.active import _worth_showing, detect_one, obsidian_vaults
from cscx.activation import ActivationError, apply_plan, plan
from cscx.color import contrast_ratio, parse_color
from cscx.editors import EDITORS, EditorPaletteError, get_editor
from cscx.editors import obsidian
from cscx.editors.groups import TREESITTER
from cscx.editors.roles import CONTRAST_TARGET, derive

FIXTURES = Path(__file__).parent / "fixtures"

_DECLARATION = re.compile(r"^  --([a-z0-9-]+): (.+);$")
_HEX = re.compile(r"#[0-9a-f]{6}\b")


def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


def light():
    """Gruvbox with its background and foreground exchanged."""
    palette = gruvbox()
    palette.background, palette.foreground = palette.foreground, palette.background
    return palette


def emit(palette=None, **kwargs):
    return get_editor("obsidian").emit(palette or gruvbox(), **kwargs)


def variables(palette=None, **kwargs):
    """The stylesheet's declarations, as `{name: value}` without the `--`."""
    found = {}
    for line in emit(palette, **kwargs).splitlines():
        if match := _DECLARATION.match(line):
            found[match.group(1)] = match.group(2)
    return found


def treesitter_fg(name):
    """What `groups.py` gives a highlight group, so the two cannot drift."""
    for group in TREESITTER:
        if group.name == name:
            return group.fg
    raise AssertionError(f"{name} is not in the treesitter table")


# -- the stylesheet -------------------------------------------------------


def test_the_stylesheet_is_comments_and_one_rule():
    """Nothing but custom properties, so there is nothing to mis-style."""
    lines = [line for line in emit().splitlines() if line]
    body = [line for line in lines if not line.startswith("/*")]

    assert body[0] == ".theme-dark {" and body[-1] == "}"
    for line in body[1:-1]:
        assert _DECLARATION.match(line), line
    assert emit().count("{") == emit().count("}") == 1


def test_the_selector_follows_the_palette_polarity():
    """Variables under `.theme-dark` apply only in dark mode, and vice versa."""
    assert ".theme-dark {" in emit(gruvbox())
    assert ".theme-light {" not in emit(gruvbox())
    assert ".theme-light {" in emit(light())
    assert ".theme-dark {" not in emit(light())


def test_every_colour_value_parses():
    for name, value in variables().items():
        if value.startswith("#"):
            assert parse_color(value) is not None, name


# -- the neutral scale ----------------------------------------------------


def test_the_scale_runs_from_background_to_foreground():
    found = variables()
    assert found["color-base-00"] == "#282828"
    assert found["color-base-100"] == "#ebdbb2"

    # Each step is no closer to the background than the one before it.
    background = parse_color("#282828")
    ratios = [
        contrast_ratio(parse_color(found[f"color-base-{step}"]), background)
        for step in obsidian.SCALE
    ]
    assert ratios == sorted(ratios)


def test_every_step_obsidian_defines_is_written():
    """A step left out would keep Obsidian's grey among this palette's."""
    assert list(obsidian.SCALE) == [
        "00", "05", "10", "20", "25", "30", "35", "40", "50", "60", "70", "100",
    ]
    assert {f"color-base-{step}" for step in obsidian.SCALE} <= set(variables())


@pytest.mark.parametrize("palette", [gruvbox, light], ids=["dark", "light"])
def test_faint_text_is_the_shade_with_guaranteed_contrast(palette):
    """Obsidian draws code comments and list markers in `--text-faint`."""
    roles = derive(palette())
    faint = parse_color(variables(palette())["color-base-50"])

    assert faint == roles["base03"]
    assert contrast_ratio(faint, roles["base00"]) >= CONTRAST_TARGET


# -- hues and the accent --------------------------------------------------


def test_the_named_hues_are_the_base16_accents():
    roles, found = derive(gruvbox()), variables()
    for hue, role in obsidian.HUES.items():
        assert found[f"color-{hue}"] == roles[role].hex


def test_pink_is_blended_from_the_hues_either_side_of_it():
    """Neither a terminal nor base16 has one, so it is made, not borrowed."""
    palette = gruvbox()
    pink = parse_color(variables()["color-pink"])
    assert pink not in palette.ansi
    assert pink not in (palette.ansi[1], palette.ansi[5])


def test_the_deprecated_rgb_forms_agree_with_the_hex_ones():
    """Plugins still read them; left alone they would be Obsidian's hues."""
    found = variables()
    for hue in (*obsidian.HUES, "pink"):
        color = parse_color(found[f"color-{hue}"])
        assert found[f"color-{hue}-rgb"] == f"{color.r}, {color.g}, {color.b}"


def test_the_accent_is_given_in_pieces_and_adds_up_to_base0D():
    """Obsidian does arithmetic on the lightness, so it wants h, s and l."""
    found = variables()
    assert found["accent-s"].endswith("%") and found["accent-l"].endswith("%")

    hue = int(found["accent-h"]) / 360
    saturation = int(found["accent-s"].rstrip("%")) / 100
    lightness = int(found["accent-l"].rstrip("%")) / 100
    rebuilt = [round(c * 255) for c in colorsys.hls_to_rgb(hue, lightness, saturation)]

    accent = derive(gruvbox())["base0D"]
    for channel, original in zip(rebuilt, (accent.r, accent.g, accent.b)):
        assert abs(channel - original) <= 3   # whole degrees and percents


@pytest.mark.parametrize("palette", [gruvbox, light], ids=["dark", "light"])
def test_text_on_the_accent_is_the_readable_end_of_the_scale(palette):
    roles = derive(palette())
    chosen = parse_color(variables(palette())["text-on-accent"])
    other = roles["base00"] if chosen == roles["base07"] else roles["base07"]

    assert chosen in (roles["base00"], roles["base07"])
    assert contrast_ratio(chosen, roles["base0D"]) >= contrast_ratio(other, roles["base0D"])


# -- agreement with the other editors -------------------------------------


@pytest.mark.parametrize("variable, group", [
    ("h1-color", "@markup.heading"),
    ("h6-color", "@markup.heading"),
    ("list-marker-color", "@markup.list"),
    ("blockquote-color", "@markup.quote"),
    ("link-color", "@markup.link.url"),
    ("link-external-color", "@markup.link.url"),
    ("code-comment", "@comment"),
    ("code-function", "@function"),
    ("code-keyword", "@keyword"),
    ("code-string", "@string"),
    ("code-operator", "@operator"),
    ("code-punctuation", "@punctuation.delimiter"),
    ("code-property", "@property"),
    ("code-tag", "@tag"),
    ("code-value", "@number"),
    ("code-important", "@string.regexp"),
])
def test_markdown_and_code_agree_with_every_other_editor(variable, group):
    assert obsidian.VARIABLES[variable] == treesitter_fg(group)
    assert variables()[variable] == derive(gruvbox())[treesitter_fg(group)].hex


def test_bold_and_italic_are_left_to_inherit():
    """cscx gives them no colour anywhere else, and neither does Obsidian."""
    assert not {"bold-color", "italic-color"} & set(variables())


def test_selection_and_cursor_are_the_terminals_own():
    found = variables()
    assert found["text-selection"] == gruvbox().selection_background.hex
    assert found["caret-color"] == gruvbox().cursor.hex


def test_selection_and_cursor_fall_back_when_the_source_lacks_them():
    palette = gruvbox()
    palette.selection_background = palette.cursor = None
    roles, found = derive(palette), variables(palette)

    assert found["text-selection"] == roles["base02"].hex
    assert found["caret-color"] == roles["base05"].hex


def test_terminal_exact_writes_only_palette_colours():
    palette = gruvbox()
    allowed = {color.hex for color in palette.ansi}
    allowed |= {
        c.hex for c in (palette.background, palette.foreground, palette.cursor,
                        palette.selection_background)
    }
    for name, value in variables(terminal_exact=True).items():
        for color in _HEX.findall(value):
            assert color in allowed, f"--{name} is {color}, which is not in the palette"


# -- hostile input, refusals, registration --------------------------------


def test_a_scheme_name_cannot_close_the_comment_it_sits_in():
    """`*/` in a name would turn the rest of the header into stylesheet."""
    palette = gruvbox()
    palette.name = "evil */ body { display: none } /*"
    output = emit(palette)

    for line in output.splitlines():
        if line.startswith("/*"):
            assert line.endswith("*/") and line.count("*/") == 1, line
    assert "display" not in "".join(
        line for line in output.splitlines() if not line.startswith("/*")
    )


def test_a_palette_missing_a_hue_is_refused_not_guessed(tmp_path):
    source = tmp_path / "partial.conf"
    source.write_text("background #000000\nforeground #ffffff\ncolor1 #ff0000\n")
    palette = parse_file(source, format="kitty")

    with pytest.raises(EditorPaletteError, match="eight normal ANSI colors"):
        emit(palette)


def test_it_is_registered_with_its_alias():
    assert "obsidian" in EDITORS
    assert get_editor("obs") is get_editor("obsidian")


def test_the_install_path_names_a_vault_it_cannot_know():
    editor = get_editor("obsidian")
    assert editor.INSTALL_PATH == "<vault>/.obsidian/themes/{name}/theme.css"
    assert editor.EXTENSION == ".css"
    assert editor.BINARY is False


def test_the_scratch_filename_is_qualified_so_it_cannot_collide():
    """`--to all` writes every target into one directory."""
    names = [e.FILENAME.format(name="x") for e in EDITORS.values()]
    assert names.count(get_editor("obsidian").FILENAME.format(name="x")) == 1


def test_the_manifest_carries_the_name_it_is_given():
    document = json.loads(obsidian.manifest("gruvbox"))
    assert document["name"] == "gruvbox"
    assert {"version", "minAppVersion", "author"} <= set(document)


# -- vaults ---------------------------------------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A throwaway HOME, with XDG overrides cleared."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return tmp_path


def make_vault(home, name, **appearance):
    vault = home / "notes" / name
    (vault / ".obsidian").mkdir(parents=True)
    if appearance:
        (vault / ".obsidian/appearance.json").write_text(json.dumps(appearance))
    return vault


def register(home, *entries):
    """Write Obsidian's own registry, `obsidian.json`."""
    registry = home / ".config/obsidian/obsidian.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({
        "vaults": {f"id{index}": entry for index, entry in enumerate(entries)}
    }))


def test_vaults_come_from_obsidians_own_registry(home):
    work, personal = make_vault(home, "Work"), make_vault(home, "Personal")
    register(
        home,
        {"path": str(work), "ts": 1},
        {"path": str(personal), "ts": 2, "open": True},
    )
    assert obsidian_vaults() == [personal, work]   # the open one first


def test_a_vault_that_no_longer_exists_is_left_out(home):
    work = make_vault(home, "Work")
    register(home, {"path": str(work)}, {"path": str(home / "deleted")})
    assert obsidian_vaults() == [work]


@pytest.mark.parametrize("content", [
    "{not json", "[]", '{"vaults": []}', '{"vaults": {"a": "nonsense"}}',
    '{"vaults": {"a": {"path": 7}}}',
])
def test_a_damaged_registry_is_no_vaults_rather_than_a_crash(home, content):
    registry = home / ".config/obsidian/obsidian.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(content)
    assert obsidian_vaults() == []


def test_no_registry_is_no_vaults(home):
    assert obsidian_vaults() == []


# -- activation -----------------------------------------------------------


def test_the_vault_is_never_guessed(home):
    """One registered vault is still not permission to write into it."""
    work = make_vault(home, "Work")
    register(home, {"path": str(work)})

    with pytest.raises(ActivationError) as caught:
        plan(gruvbox(), "obsidian")
    assert "--vault" in str(caught.value)
    assert str(work) in str(caught.value)      # but it does say which exist
    assert not (work / ".obsidian/themes").exists()


def test_a_directory_that_is_not_a_vault_is_refused(home):
    (home / "plain").mkdir()
    with pytest.raises(ActivationError, match="not an Obsidian vault"):
        plan(gruvbox(), "obsidian", vault=home / "plain")


def test_a_theme_is_a_stylesheet_and_a_manifest_named_alike(home):
    vault = make_vault(home, "Work")
    proposed = plan(gruvbox(), "obsidian", name="Gruvbox Dark", vault=vault)
    apply_plan(proposed)

    root = vault / ".obsidian/themes/gruvbox-dark"
    assert sorted(p.name for p in root.iterdir()) == ["manifest.json", "theme.css"]
    # Obsidian matches the directory against the manifest exactly.
    assert json.loads((root / "manifest.json").read_text())["name"] == root.name
    assert proposed.theme_path == root / "theme.css"
    # --name reaches the header too, so the file agrees with where it lives.
    assert (root / "theme.css").read_text().startswith("/* gruvbox-dark */")


def test_activation_does_not_select_the_theme(home):
    """Choosing one stays a deliberate act, as it does for every editor."""
    vault = make_vault(home, "Work", theme="obsidian", cssTheme="Minimal")
    before = (vault / ".obsidian/appearance.json").read_text()

    proposed = plan(gruvbox(), "obsidian", vault=vault)
    apply_plan(proposed)

    assert (vault / ".obsidian/appearance.json").read_text() == before
    assert "Appearance" in proposed.reload and "Dark" in proposed.reload


def test_a_vault_in_the_other_polarity_is_pointed_out(home):
    """A dark theme in a light vault installs and then visibly does nothing."""
    light_vault = make_vault(home, "Light", theme="moonstone")
    dark_vault = make_vault(home, "Dark", theme="obsidian")
    unset = make_vault(home, "Unset")

    assert "light" in plan(gruvbox(), "obsidian", vault=light_vault).warnings[0]
    assert plan(gruvbox(), "obsidian", vault=dark_vault).warnings == []
    assert plan(gruvbox(), "obsidian", vault=unset).warnings == []
    assert "dark" in plan(light(), "obsidian", vault=dark_vault).warnings[0]


def test_activating_again_is_reported_as_an_edit(home):
    vault = make_vault(home, "Work")
    first = plan(gruvbox(), "obsidian", vault=vault)
    assert not any(step.edits_existing for step in first.steps)
    apply_plan(first)

    assert all(step.edits_existing for step in plan(gruvbox(), "obsidian", vault=vault).steps)


def test_the_cli_takes_the_vault(home, capsys):
    from cscx.cli import main

    vault = make_vault(home, "Work")
    source = str(FIXTURES / "gruvbox.kitty.conf")

    assert main(["activate", source, "--for", "obsidian"]) == 1
    assert "--vault" in capsys.readouterr().err

    assert main(["activate", source, "--for", "obsidian", "--vault", str(vault)]) == 0
    assert (vault / ".obsidian/themes/gruvbox-kitty/theme.css").is_file()


# -- detection ------------------------------------------------------------


def test_each_vault_reports_its_own_theme(home):
    work = make_vault(home, "Work", cssTheme="Notation")
    personal = make_vault(home, "Personal", cssTheme="gruvbox")
    theme = personal / ".obsidian/themes/gruvbox/theme.css"
    theme.parent.mkdir(parents=True)
    theme.write_text(emit())
    register(home, {"path": str(work), "ts": 2}, {"path": str(personal), "ts": 1})

    found = {entry.note: entry for entry in detect_one("obsidian")}
    assert found["vault Work"].name == "Notation"
    assert found["vault Work"].path is None          # set, but not on disk
    assert found["vault Personal"].name == "gruvbox"
    assert found["vault Personal"].path == theme


def test_a_vault_on_the_default_theme_is_left_out_of_the_sweep(home):
    register(home, {"path": str(make_vault(home, "Work"))})

    entry = detect_one("obsidian")[0]
    assert entry.name is None
    assert not _worth_showing(entry)


def test_no_vaults_at_all_is_an_absent_application(home):
    assert not _worth_showing(detect_one("obsidian")[0])
