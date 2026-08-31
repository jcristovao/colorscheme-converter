"""The editor layer: role derivation, colour maths, and themes that load."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.color import Color, contrast_ratio, is_dark, luminance, mix, parse_color
from cscx.cterm import cterm_index
from cscx.editors import EDITORS, EditorPaletteError, emit_theme, get_editor
from cscx.editors.groups import CORE, DIAGNOSTICS, LSP_LINKS, NEOVIM_UI, TREESITTER
from cscx.editors.roles import COMMENT_BLEND_CEILING, CONTRAST_TARGET, derive
from cscx.fill import fill

FIXTURES = Path(__file__).parent / "fixtures"
BASE16 = [f"base0{c}" for c in "0123456789ABCDEF"]
OPTIONAL_ROLES = {"cursor", "cursor_text", "selection_bg", "selection_fg"}


@pytest.fixture
def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


# -- colour maths ---------------------------------------------------------

def test_mix_returns_the_endpoints_exactly():
    black, white = Color(0, 0, 0), Color(255, 255, 255)
    assert mix(black, white, 0.0) == black
    assert mix(black, white, 1.0) == white


def test_mix_clamps_out_of_range_factors():
    black, white = Color(0, 0, 0), Color(255, 255, 255)
    assert mix(black, white, -1.0) == black
    assert mix(black, white, 5.0) == white


def test_mix_does_not_overshoot_the_way_linear_light_does():
    """The reason for OKLab: linear light blows past the perceptual middle."""
    middle = mix(Color(0, 0, 0), Color(255, 255, 255), 0.5)
    assert middle.r == middle.g == middle.b
    # Linear-light interpolation lands near #bcbcbc (188) -- far too light for
    # a UI ramp. OKLab stays well below that.
    assert middle.r < 150


def test_small_steps_stay_subtle():
    """A 10% step is a cursorline, and must not read as a different theme."""
    bg, fg = parse_color("#282828"), parse_color("#ebdbb2")
    assert contrast_ratio(mix(bg, fg, 0.10), bg) < 1.5


def test_mix_steps_are_monotonic():
    bg, fg = parse_color("#282828"), parse_color("#ebdbb2")
    ratios = [contrast_ratio(mix(bg, fg, t / 10), bg) for t in range(11)]
    assert ratios == sorted(ratios)


def test_contrast_ratio_matches_the_wcag_extremes():
    black, white = Color(0, 0, 0), Color(255, 255, 255)
    assert contrast_ratio(black, white) == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio(white, white) == pytest.approx(1.0)
    # The ratio is defined regardless of argument order.
    assert contrast_ratio(black, white) == contrast_ratio(white, black)


def test_luminance_and_darkness():
    assert luminance(Color(0, 0, 0)) == pytest.approx(0.0)
    assert luminance(Color(255, 255, 255)) == pytest.approx(1.0)
    assert is_dark(parse_color("#282828"))
    assert not is_dark(parse_color("#fdf6e3"))


# -- cterm ----------------------------------------------------------------

def test_palette_colours_map_to_their_own_ansi_index(gruvbox):
    """A scheme colour must use the terminal's own slot, not the 256-cube."""
    for index, color in enumerate(gruvbox.ansi):
        assert cterm_index(color, gruvbox) == index


def test_derived_colours_fall_back_to_the_extended_range(gruvbox):
    derived_grey = mix(gruvbox.background, gruvbox.foreground, 0.5)
    assert cterm_index(derived_grey, gruvbox) >= 16


def test_pure_grey_lands_on_the_grey_ramp(gruvbox):
    # 232-255 is the grey ramp; 8 + 10*n.
    assert cterm_index(Color(18, 18, 18), gruvbox) in range(232, 256)


# -- role derivation ------------------------------------------------------

def test_every_base16_role_is_assigned(gruvbox):
    roles = derive(gruvbox)
    assert set(BASE16) <= set(roles.slots)


def test_background_and_foreground_are_taken_verbatim(gruvbox):
    roles = derive(gruvbox)
    assert roles["base00"] == gruvbox.background
    assert roles["base05"] == gruvbox.foreground


@pytest.mark.parametrize(
    "role,index",
    [("base08", 1), ("base0A", 3), ("base0B", 2),
     ("base0C", 6), ("base0D", 4), ("base0E", 5)],
)
def test_accents_come_from_the_matching_ansi_hue(gruvbox, role, index):
    assert derive(gruvbox)[role] == gruvbox.ansi[index]


def test_terminal_selection_and_cursor_carry_through(gruvbox):
    roles = derive(gruvbox)
    assert roles["selection_bg"] == gruvbox.selection_background
    assert roles["cursor"] == gruvbox.cursor


def test_optional_roles_are_absent_when_the_source_lacks_them():
    konsole = parse_file(FIXTURES / "gruvbox.colorscheme")  # no cursor/selection
    roles = derive(konsole)
    assert not (OPTIONAL_ROLES & set(roles.slots))
    # Visual must still resolve, via its base02 fallback.
    assert roles.resolve("selection_bg|base02") == roles["base02"]


def test_comments_meet_the_contrast_target(gruvbox):
    roles = derive(gruvbox)
    assert contrast_ratio(roles["base03"], roles["base00"]) >= CONTRAST_TARGET
    assert not roles.warnings


def test_low_contrast_schemes_are_capped_and_reported():
    """Comments must never be pushed on top of normal text to hit a ratio."""
    flat = parse_file(FIXTURES / "gruvbox.kitty.conf")
    flat.foreground = parse_color("#3c3c3c")  # barely above the background
    roles = derive(flat)

    ceiling = mix(roles["base00"], roles["base05"], COMMENT_BLEND_CEILING)
    assert roles["base03"] == ceiling
    assert roles["base03"] != roles["base05"]
    assert any("short of" in w for w in roles.warnings)


def test_contrast_target_is_configurable(gruvbox):
    relaxed = derive(gruvbox, contrast_target=1.0)
    strict = derive(gruvbox, contrast_target=7.0)
    # A higher target pushes comments further from the background.
    assert contrast_ratio(strict["base03"], strict["base00"]) > \
        contrast_ratio(relaxed["base03"], relaxed["base00"])


def test_terminal_exact_uses_only_palette_colours(gruvbox):
    roles = derive(gruvbox, terminal_exact=True)
    allowed = {c.hex for c in gruvbox.ansi}
    allowed |= {gruvbox.background.hex, gruvbox.foreground.hex}
    allowed |= {c.hex for c in (gruvbox.cursor, gruvbox.cursor_text,
                                gruvbox.selection_background,
                                gruvbox.selection_foreground) if c}
    for role in BASE16:
        assert roles[role].hex in allowed, f"{role} is not a palette colour"


def test_terminal_exact_warns_when_color0_is_the_background(gruvbox):
    roles = derive(gruvbox, terminal_exact=True)
    assert any("invisible" in w for w in roles.warnings)


def test_light_and_dark_backgrounds_are_distinguished(gruvbox):
    assert derive(gruvbox).background_is_dark

    light = parse_file(FIXTURES / "gruvbox.kitty.conf")
    light.background, light.foreground = light.foreground, light.background
    assert not derive(light).background_is_dark


def test_an_incomplete_palette_is_refused_with_advice(tmp_path):
    """The eight normal slots are the floor; everything else --fill can supply."""
    source = tmp_path / "partial.conf"
    source.write_text("\n".join(
        f"color{i} #{i * 17:02x}{i * 17:02x}{i * 17:02x}" for i in range(8)
    ))
    palette = parse_file(source, format="kitty")
    assert palette.foreground is None

    with pytest.raises(EditorPaletteError, match="--fill"):
        derive(palette)

    # And --fill is genuinely the fix it points at.
    filled, _ = fill(palette)
    roles = derive(filled)
    assert roles["base00"] == filled.ansi[0]
    assert roles["base05"] == filled.ansi[7]


# -- group tables ---------------------------------------------------------

ALL_GROUPS = CORE + NEOVIM_UI + TREESITTER + LSP_LINKS + DIAGNOSTICS


def test_no_group_references_an_unknown_role():
    """Catches a typo like `base0G`, which would silently drop a colour."""
    known = set(BASE16) | OPTIONAL_ROLES
    for group in ALL_GROUPS:
        for chain in (group.fg, group.bg, group.sp):
            for role in (chain or "").split("|"):
                if role:
                    assert role in known, f"{group.name} references {role!r}"


def test_group_names_are_unique_within_each_table():
    for table in (CORE, NEOVIM_UI, TREESITTER, LSP_LINKS, DIAGNOSTICS):
        names = [g.name for g in table]
        assert len(names) == len(set(names))


def test_every_link_target_is_a_group_we_define():
    defined = {g.name for g in ALL_GROUPS}
    for group in ALL_GROUPS:
        if group.link:
            assert group.link in defined, f"{group.name} links to undefined {group.link}"


def test_every_group_produces_something(gruvbox):
    """A group with no colour and no attributes would be dead weight."""
    for group in ALL_GROUPS:
        assert group.link or group.fg or group.bg or group.sp or group.attrs


# -- generated files ------------------------------------------------------

@pytest.mark.parametrize("editor", sorted(EDITORS))
def test_theme_declares_its_name_and_background(gruvbox, editor):
    gruvbox.name = "Test Scheme"
    output = emit_theme(gruvbox, editor)
    assert "test-scheme" in output          # slugified for vim
    assert "dark" in output


def test_vim_output_sets_gui_and_cterm_colours(gruvbox):
    output = emit_theme(gruvbox, "vim")
    assert re.search(r"^hi Normal .*guifg=#ebdbb2 guibg=#282828", output, re.M)
    # String is ANSI green, so it must use the terminal's own slot 2.
    assert re.search(r"^hi String .*ctermfg=2\b", output, re.M)
    assert "let g:terminal_ansi_colors = [" in output


def test_neovim_output_uses_set_hl_and_links(gruvbox):
    output = emit_theme(gruvbox, "neovim")
    assert 'hl(0, "Normal", { fg = "#ebdbb2", bg = "#282828"' in output
    assert 'hl(0, "@lsp.type.parameter", { link = "@variable.parameter" })' in output
    assert 'vim.g.terminal_color_1 = "#cc241d"' in output


def test_neovim_does_not_force_termguicolors(gruvbox):
    """That is the user's setting, not a colorscheme's to make."""
    assert "termguicolors" not in emit_theme(gruvbox, "neovim")


@pytest.mark.parametrize("editor", sorted(EDITORS))
def test_header_records_where_each_role_came_from(gruvbox, editor):
    output = emit_theme(gruvbox, editor)
    assert "base00" in output and "background" in output
    assert "OKLab" in output


@pytest.mark.parametrize("editor", sorted(EDITORS))
def test_warnings_reach_the_generated_file(gruvbox, editor):
    output = emit_theme(gruvbox, editor, terminal_exact=True)
    assert "NOTE:" in output


def test_a_missing_hue_is_refused_without_suggesting_fill(tmp_path):
    """--fill cannot conjure a hue, so the error must not recommend it."""
    source = tmp_path / "nohue.conf"
    source.write_text("\n".join(
        f"color{i} #{i * 17:02x}{i * 17:02x}{i * 17:02x}"
        for i in range(8) if i != 3          # no yellow
    ))
    palette = parse_file(source, format="kitty")
    filled, _ = fill(palette)

    with pytest.raises(EditorPaletteError) as caught:
        derive(filled)
    assert "color3" in str(caught.value)
    assert "--fill" not in str(caught.value)


def test_unknown_editor_is_rejected():
    with pytest.raises(KeyError, match="unknown editor"):
        get_editor("emacs")


def test_editor_aliases_resolve():
    assert get_editor("nvim").NAME == "neovim"
    assert get_editor("vi").NAME == "vim"


# -- the real editors -----------------------------------------------------

def _write_theme(tmp_path, editor, palette, **kwargs):
    path = tmp_path / f"scheme{get_editor(editor).EXTENSION}"
    path.write_text(emit_theme(palette, editor, **kwargs))
    return path


@pytest.mark.skipif(not shutil.which("vim"), reason="vim not installed")
@pytest.mark.parametrize("exact", [False, True])
def test_vim_loads_the_theme_without_errors(gruvbox, tmp_path, exact):
    theme = _write_theme(tmp_path, "vim", gruvbox, terminal_exact=exact)
    dump = tmp_path / "dump.txt"
    result = subprocess.run(
        ["vim", "-es", "-u", "NONE", "--not-a-term",
         "-c", f"source {theme}",
         "-c", f"redir! > {dump}",
         "-c", "silent hi Normal", "-c", "silent echo g:colors_name",
         "-c", "redir END", "-c", "qa!"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert not result.stderr.strip(), result.stderr
    text = dump.read_text()
    assert "guifg=#ebdbb2" in text and "guibg=#282828" in text


@pytest.mark.skipif(not shutil.which("nvim"), reason="neovim not installed")
@pytest.mark.parametrize("exact", [False, True])
def test_neovim_loads_the_theme_without_errors(gruvbox, tmp_path, exact):
    theme = _write_theme(tmp_path, "neovim", gruvbox, terminal_exact=exact)
    probe = (
        'local n = vim.api.nvim_get_hl(0, { name = "Normal" }) '
        'assert(n.fg == 0xebdbb2 and n.bg == 0x282828, "Normal wrong") '
        'local p = vim.api.nvim_get_hl(0, { name = "@lsp.type.parameter" }) '
        'assert(p.link == "@variable.parameter", "lsp link wrong") '
        'assert(vim.g.colors_name, "no colors_name")'
    )
    result = subprocess.run(
        ["nvim", "--headless", "-u", "NONE", "--noplugin",
         "-c", f"luafile {theme}", "-c", f"lua {probe}", "-c", "qa!"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "E5" not in result.stderr and "Error" not in result.stderr, result.stderr


# -- hostile input --------------------------------------------------------

HOSTILE_NAME = 'evil" name\n-- with newline\rand \\ backslash\x00and a nul'


def test_single_line_flattens_control_characters():
    from cscx._text import single_line

    assert "\n" not in single_line(HOSTILE_NAME)
    assert "\x00" not in single_line(HOSTILE_NAME)
    assert single_line(None) == ""
    assert single_line("  spaced   out  ") == "spaced out"
    assert len(single_line("x" * 500)) <= 120


def test_toml_string_escapes_quotes_and_backslashes():
    from cscx._text import toml_string

    assert toml_string('a "b" c') == '"a \\"b\\" c"'
    assert toml_string("back\\slash") == '"back\\\\slash"'


@pytest.mark.parametrize("editor", sorted(EDITORS))
def test_a_hostile_scheme_name_cannot_break_the_output(gruvbox, editor):
    """A newline in the name would end the comment and run the rest as code."""
    gruvbox.name = HOSTILE_NAME
    output = emit_theme(gruvbox, editor)
    comment = "--" if editor == "neovim" else '"'
    for line in output.splitlines():
        if line and not line.startswith(comment):
            assert "evil" not in line or "colors_name" in line


@pytest.mark.skipif(not shutil.which("nvim"), reason="neovim not installed")
def test_neovim_loads_a_theme_with_a_hostile_name(gruvbox, tmp_path):
    gruvbox.name = HOSTILE_NAME
    theme = _write_theme(tmp_path, "neovim", gruvbox)
    result = subprocess.run(
        ["nvim", "--headless", "-u", "NONE", "--noplugin",
         "-c", f"luafile {theme}", "-c", "qa!"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr.strip(), result.stderr


@pytest.mark.skipif(not shutil.which("vim"), reason="vim not installed")
def test_vim_loads_a_theme_with_a_hostile_name(gruvbox, tmp_path):
    gruvbox.name = HOSTILE_NAME
    theme = _write_theme(tmp_path, "vim", gruvbox)
    result = subprocess.run(
        ["vim", "-es", "-u", "NONE", "--not-a-term",
         "-c", f"source {theme}", "-c", "qa!"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert not result.stderr.strip(), result.stderr
