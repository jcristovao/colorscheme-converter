"""The ghostwriter writer.

ghostwriter has no syntax groups, so there is no group table to check. What
matters instead is that the eleven colours it does have agree with the
decisions this project already made for every other editor, and that the
document satisfies its loader -- which ands its per-key results together and
rejects the whole file if any one of them is missing or unparseable.
"""

import json
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.color import ColorParseError, parse_color
from cscx.editors import EDITORS, EditorPaletteError, get_editor
from cscx.editors import ghostwriter as gw
from cscx.editors.groups import TREESITTER
from cscx.editors.roles import derive

FIXTURES = Path(__file__).parent / "fixtures"

#: Exactly the keys ghostwriter's `loadColorsFromJsonObject` reads. It requires
#: every one of them, so this is both a floor and a ceiling.
KEYS = {
    "background", "foreground", "selection", "cursor", "markup", "accent",
    "heading", "emphasis", "block", "link", "error",
}


def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


def emit(palette=None, **kwargs):
    return json.loads(get_editor("ghostwriter").emit(palette or gruvbox(), **kwargs))


def treesitter_fg(name):
    """What `groups.py` gives a highlight group, so the two cannot drift."""
    for group in TREESITTER:
        if group.name == name:
            return group.fg
    raise AssertionError(f"{name} is not in the treesitter table")


# -- the document ---------------------------------------------------------


def test_every_key_the_loader_requires_is_present_and_no_others():
    """ghostwriter ands its per-key results, so one gap rejects the file."""
    assert set(emit()) == KEYS


def test_values_are_hex_colours():
    for key, value in emit().items():
        assert value.startswith("#") and len(value) == 7, f"{key} = {value!r}"
        parse_color(value)  # raises if ghostwriter's QColor would refuse it


def test_the_document_is_a_single_scheme_not_a_light_dark_pair():
    """A palette has one polarity; claiming a dark scheme would invent one.

    ghostwriter accepts this form and responds by ignoring its dark mode
    toggle, which is what its own tooltip tells the user to expect.
    """
    document = emit()
    assert "light" not in document and "dark" not in document


def test_the_theme_is_named_by_its_filename_alone():
    """Nothing inside the document records the name: the loader uses the stem."""
    palette = gruvbox()
    palette.name = "My Theme"
    assert "name" not in emit(palette)
    assert gw.theme_name(palette) == "my-theme"
    # Where ghostwriter actually looks, the file must carry the bare name.
    editor = get_editor("ghostwriter")
    assert editor.INSTALL_PATH.format(name="my-theme").endswith("/my-theme.json")


def test_the_scratch_filename_is_qualified_so_it_cannot_collide():
    """`--to all` writes every target into one directory.

    Claude Code also wants `{name}.json` there, and a collision means one of
    the two silently does not get written -- so only the install path keeps
    the bare name ghostwriter requires.
    """
    from cscx.editors import EDITORS as ALL

    filenames = [e.FILENAME for e in {v for v in ALL.values()}]
    assert get_editor("ghostwriter").FILENAME == "{name}.ghostwriter.json"
    assert filenames.count("{name}.json") == 1  # claude-code, alone


def test_a_hostile_scheme_name_cannot_reach_the_document():
    palette = gruvbox()
    palette.name = 'evil", "background": "#ff0000'
    document = emit(palette)
    assert document["background"] == palette.background.hex
    assert set(document) == KEYS


# -- the mapping ----------------------------------------------------------


def test_the_palette_values_are_carried_through_verbatim():
    palette = gruvbox()
    document = emit(palette)
    assert document["background"] == palette.background.hex
    assert document["foreground"] == palette.foreground.hex
    assert document["selection"] == palette.selection_background.hex
    assert document["cursor"] == palette.cursor.hex


@pytest.mark.parametrize("key, group", [
    ("heading", "@markup.heading"),
    ("accent", "@markup.list"),
    ("block", "@markup.quote"),
    ("link", "@markup.link.url"),
])
def test_the_markdown_colours_agree_with_every_other_editor(key, group):
    """The point of the mapping: one palette dresses all the editors alike.

    If someone retunes `@markup.heading` in groups.py, a ghostwriter theme
    generated from the same palette has to follow, or the two disagree about
    what a heading looks like with nothing to say why.
    """
    assert gw.COLORS[key] == treesitter_fg(group)


def test_markup_takes_the_one_shade_whose_contrast_is_guaranteed():
    """`markup` is every syntax character at once, so it must stay readable.

    base03 is searched until it clears the contrast target; every other
    recessive candidate is merely interpolated and hoped for.
    """
    assert gw.COLORS["markup"] == "base03"
    roles = derive(gruvbox())
    assert emit()["markup"] == roles["base03"].hex


def test_selection_and_cursor_fall_back_when_the_source_lacks_them():
    palette = parse_file(FIXTURES / "gruvbox.colorscheme")  # no cursor/selection
    assert palette.cursor is None and palette.selection_background is None

    roles = derive(palette)
    document = emit(palette)
    assert document["selection"] == roles["base02"].hex
    assert document["cursor"] == roles["base0D"].hex


def test_terminal_exact_is_honoured():
    exact = emit(terminal_exact=True)
    assert exact["selection"] == gruvbox().selection_background.hex
    assert exact != emit()


# -- refusals and registration --------------------------------------------


def test_a_palette_missing_a_hue_is_refused_not_guessed(tmp_path):
    source = tmp_path / "partial.conf"
    source.write_text("background #000000\nforeground #ffffff\ncolor1 #ff0000\n")
    palette = parse_file(source, format="kitty")

    with pytest.raises(EditorPaletteError, match="eight normal ANSI colors"):
        emit(palette)


def test_it_is_registered_with_its_alias():
    assert "ghostwriter" in EDITORS
    assert get_editor("gw") is get_editor("ghostwriter")


def test_it_installs_where_ghostwriter_actually_looks():
    """ThemeRepository lists *.json from this directory and nowhere else."""
    editor = get_editor("ghostwriter")
    assert editor.INSTALL_PATH == "~/.local/share/ghostwriter/themes/{name}.json"
    assert editor.EXTENSION == ".json"
    assert editor.BINARY is False


def test_the_loader_would_accept_what_we_write():
    """Re-implements ghostwriter's own validation, which is strict and total.

    `loadColor` fails a key that is undefined, not a string, or not a valid
    colour name; `loadColorsFromJsonObject` ands all eleven together.
    """
    document = emit()
    valid = True
    for key in KEYS:
        value = document.get(key)
        if not isinstance(value, str):
            valid = False
            continue
        try:
            parse_color(value)
        except ColorParseError:
            valid = False
    assert valid
