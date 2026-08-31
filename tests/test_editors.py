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

#: How each generated theme opens a comment. `None` means the format has no
#: comment syntax, so provenance and warnings cannot be written into the file
#: and are reported on stderr instead.
COMMENT_PREFIX = {
    "vim": '"', "neovim": "--", "helix": "#", "emacs": ";;",
    "vscode": None, "cursor": None, "antigravity": None,
}
COMMENTED = sorted(e for e, c in COMMENT_PREFIX.items() if c)
UNCOMMENTED = sorted(e for e, c in COMMENT_PREFIX.items() if not c)


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
    # vim, neovim, helix and emacs need a slug they can use as an identifier;
    # VS Code shows the name to the user and keeps it as written.
    assert "test-scheme" in output or "Test Scheme" in output
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


@pytest.mark.parametrize("editor", COMMENTED)
def test_header_records_where_each_role_came_from(gruvbox, editor):
    output = emit_theme(gruvbox, editor)
    assert "base00" in output and "background" in output
    assert "OKLab" in output


@pytest.mark.parametrize("editor", COMMENTED)
def test_warnings_reach_the_generated_file(gruvbox, editor):
    output = emit_theme(gruvbox, editor, terminal_exact=True)
    assert "NOTE:" in output


@pytest.mark.parametrize("editor", UNCOMMENTED)
def test_warnings_are_still_reachable_for_commentless_formats(gruvbox, editor):
    """VS Code themes are plain JSON, so callers need the warnings directly."""
    from cscx.editors import theme_warnings

    assert "NOTE" not in emit_theme(gruvbox, editor, terminal_exact=True)
    assert theme_warnings(gruvbox, terminal_exact=True)


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
        get_editor("notepad")


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
    comment = COMMENT_PREFIX[editor]
    if comment is None:
        # No comments to break out of; it only has to stay valid JSON.
        import json

        assert json.loads(output)["name"]
        return
    for line in output.splitlines():
        if line and not line.startswith(comment):
            # Outside comments the name may only appear slugified. The quote is
            # the marker: slugging replaces it, so its presence means the raw
            # name reached a place where it could break out.
            assert 'evil"' not in line


def test_every_editor_has_a_known_comment_prefix():
    """Guards the test above from silently skipping a newly added editor."""
    assert set(COMMENT_PREFIX) == set(EDITORS)


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


# -- helix ----------------------------------------------------------------

# Verbatim from the Helix theme reference. Helix is not installed here, so a
# scope name typo cannot be caught by loading the theme -- this list is the
# substitute for that check.
HELIX_SCOPES = {
    "attribute", "type", "type.builtin", "type.parameter", "type.enum",
    "type.enum.variant", "constructor", "constant", "constant.builtin",
    "constant.builtin.boolean", "constant.character", "constant.character.escape",
    "constant.numeric", "constant.numeric.integer", "constant.numeric.float",
    "string", "string.regexp", "string.special", "string.special.path",
    "string.special.url", "string.special.symbol", "comment", "comment.line",
    "comment.line.documentation", "comment.block", "comment.block.documentation",
    "comment.unused", "variable", "variable.builtin", "variable.parameter",
    "variable.other", "variable.other.member", "variable.other.member.private",
    "label", "punctuation", "punctuation.delimiter", "punctuation.bracket",
    "punctuation.special", "keyword", "keyword.control",
    "keyword.control.conditional", "keyword.control.repeat",
    "keyword.control.import", "keyword.control.return",
    "keyword.control.exception", "keyword.operator", "keyword.directive",
    "keyword.function", "keyword.storage", "keyword.storage.type",
    "keyword.storage.modifier", "operator", "function", "function.builtin",
    "function.method", "function.method.private", "function.macro",
    "function.special", "tag", "tag.builtin", "namespace", "special",
    "markup", "markup.heading", "markup.heading.marker", "markup.heading.1",
    "markup.heading.2", "markup.heading.3", "markup.heading.4",
    "markup.heading.5", "markup.heading.6", "markup.list",
    "markup.list.unnumbered", "markup.list.numbered", "markup.list.checked",
    "markup.list.unchecked", "markup.bold", "markup.italic",
    "markup.strikethrough", "markup.link", "markup.link.url",
    "markup.link.label", "markup.link.text", "markup.quote", "markup.raw",
    "markup.raw.inline", "markup.raw.block", "diff", "diff.plus",
    "diff.plus.gutter", "diff.minus", "diff.minus.gutter", "diff.delta",
    "diff.delta.moved", "diff.delta.conflict", "diff.delta.gutter",
    "ui.background", "ui.background.separator", "ui.cursor", "ui.cursor.normal",
    "ui.cursor.insert", "ui.cursor.select", "ui.cursor.match",
    "ui.cursor.primary", "ui.cursor.primary.normal", "ui.cursor.primary.insert",
    "ui.cursor.primary.select", "ui.debug.breakpoint", "ui.debug.active",
    "ui.gutter", "ui.gutter.selected", "ui.linenr", "ui.linenr.selected",
    "ui.statusline", "ui.statusline.inactive", "ui.statusline.normal",
    "ui.statusline.insert", "ui.statusline.select", "ui.statusline.separator",
    "ui.bufferline", "ui.bufferline.active", "ui.bufferline.background",
    "ui.popup", "ui.popup.info", "ui.picker.header", "ui.picker.header.column",
    "ui.picker.header.column.active", "ui.window", "ui.help", "ui.text",
    "ui.text.focus", "ui.text.inactive", "ui.text.info", "ui.text.directory",
    "ui.virtual.ruler", "ui.virtual.whitespace", "ui.virtual.indent-guide",
    "ui.virtual.inlay-hint", "ui.virtual.inlay-hint.parameter",
    "ui.virtual.inlay-hint.type", "ui.virtual.wrap", "ui.virtual.jump-label",
    "ui.menu", "ui.menu.selected", "ui.menu.scroll", "ui.selection",
    "ui.selection.primary", "ui.highlight", "ui.highlight.frameline",
    "ui.cursorline.primary", "ui.cursorline.secondary",
    "ui.cursorcolumn.primary", "ui.cursorcolumn.secondary",
    "warning", "error", "info", "hint", "diagnostic", "diagnostic.hint",
    "diagnostic.info", "diagnostic.warning", "diagnostic.error",
    "diagnostic.unnecessary", "diagnostic.deprecated", "tabstop",
}

HELIX_MODIFIERS = {
    "bold", "dim", "italic", "underlined", "slow_blink", "rapid_blink",
    "reversed", "hidden", "crossed_out",
}
HELIX_UNDERLINE_STYLES = {"line", "curl", "dashed", "dotted", "double_line"}


@pytest.fixture
def helix_theme(gruvbox):
    import tomllib

    return tomllib.loads(emit_theme(gruvbox, "helix"))


def test_helix_output_is_valid_toml(helix_theme):
    assert "palette" in helix_theme
    assert helix_theme["ui.background"] == {"bg": "base00"}


def test_helix_scope_names_are_all_real(helix_theme):
    from cscx.editors.groups import HELIX

    for group in HELIX:
        assert group.name in HELIX_SCOPES, f"{group.name!r} is not a Helix scope"
    # And nothing extra leaked into the file beyond the scopes and the palette.
    assert set(helix_theme) - {"palette"} <= HELIX_SCOPES


def test_every_helix_colour_reference_exists_in_the_palette(helix_theme):
    """A dangling palette name would make Helix reject the whole theme."""
    palette = helix_theme["palette"]
    for scope, value in helix_theme.items():
        if scope == "palette":
            continue
        if isinstance(value, str):
            assert value in palette, f"{scope} -> {value}"
            continue
        for key in ("fg", "bg"):
            if key in value:
                assert value[key] in palette, f"{scope}.{key} -> {value[key]}"
        if "color" in value.get("underline", {}):
            assert value["underline"]["color"] in palette


def test_helix_modifiers_and_underline_styles_are_valid(helix_theme):
    for scope, value in helix_theme.items():
        if scope == "palette" or isinstance(value, str):
            continue
        for modifier in value.get("modifiers", []):
            assert modifier in HELIX_MODIFIERS, f"{scope}: {modifier}"
        if underline := value.get("underline"):
            assert underline["style"] in HELIX_UNDERLINE_STYLES


def test_helix_palette_comes_last(gruvbox):
    """A bare key after `[palette]` would be swallowed into that table."""
    lines = [l for l in emit_theme(gruvbox, "helix").splitlines()
             if l and not l.startswith("#")]
    header = lines.index("[palette]")
    assert all("=" in l for l in lines[header + 1:])
    assert all(l.startswith('"') for l in lines[:header])


def test_helix_uses_the_shorthand_for_foreground_only_scopes(gruvbox):
    output = emit_theme(gruvbox, "helix")
    assert '"keyword" = "base0E"' in output
    assert '"comment" = { fg = "base03", modifiers = ["italic"] }' in output


def test_helix_undercurl_becomes_an_underline_style(gruvbox):
    output = emit_theme(gruvbox, "helix")
    assert '"diagnostic.error" = { underline = { color = "base08", style = "curl" } }' in output


def test_helix_terminal_exact_still_parses(gruvbox):
    import tomllib

    doc = tomllib.loads(emit_theme(gruvbox, "helix", terminal_exact=True))
    palette = doc["palette"]
    allowed = {c.hex for c in gruvbox.ansi} | {gruvbox.background.hex, gruvbox.foreground.hex}
    allowed |= {c.hex for c in (gruvbox.cursor, gruvbox.cursor_text,
                                gruvbox.selection_background,
                                gruvbox.selection_foreground) if c}
    for role, value in palette.items():
        if role.startswith("base"):
            assert value in allowed, f"{role} is not a palette colour"


def test_helix_alias_resolves():
    assert get_editor("hx").NAME == "helix"


# -- emacs ----------------------------------------------------------------


def read_sexps(text):
    """A minimal s-expression reader, to prove the Elisp is well formed.

    Emacs is not installed here, so the generated theme cannot be checked by
    loading it. Unbalanced parens and an unescaped quote inside a string are
    the two ways this writer could plausibly break, and both show up here.
    """
    forms, stack, current, index = [], [], None, 0
    while index < len(text):
        char = text[index]
        if char == ";":
            index = text.find("\n", index)
            if index == -1:
                break
            continue
        if char == '"':
            index += 1
            while index < len(text) and text[index] != '"':
                index += 2 if text[index] == "\\" else 1
            assert index < len(text), "unterminated string"
            index += 1
            continue
        if char in "([":
            stack.append(char)
            if len(stack) == 1:
                current = index
        elif char in ")]":
            assert stack, f"unbalanced close at offset {index}"
            opened = stack.pop()
            assert (opened, char) in {("(", ")"), ("[", "]")}, "mismatched bracket"
            if not stack:
                forms.append(text[current:index + 1])
        index += 1
    assert not stack, "unbalanced open parenthesis"
    return forms


def test_emacs_output_is_well_formed_elisp(gruvbox):
    forms = read_sexps(emit_theme(gruvbox, "emacs"))
    heads = [f.split(None, 1)[0].lstrip("(") for f in forms]
    assert heads == [
        "deftheme", "custom-theme-set-faces", "custom-theme-set-variables",
        "provide-theme",
    ]


def test_emacs_theme_name_is_a_valid_symbol(gruvbox):
    gruvbox.name = "Test Scheme"
    output = emit_theme(gruvbox, "emacs")
    assert "(deftheme test-scheme" in output
    assert "(provide-theme 'test-scheme)" in output
    assert output.startswith(";;; test-scheme-theme.el")
    assert output.rstrip().endswith(";;; test-scheme-theme.el ends here")


def test_emacs_faces_carry_colours_and_attributes(gruvbox):
    output = emit_theme(gruvbox, "emacs")
    assert ''''(default ((t (:foreground "#ebdbb2" :background "#282828"))))''' in output
    assert ":slant italic" in output
    assert ":weight bold" in output


def test_emacs_sets_the_ansi_colour_vector(gruvbox):
    """So shell and compilation buffers match the source terminal."""
    output = emit_theme(gruvbox, "emacs")
    assert "ansi-color-names-vector" in output
    vector = output.split("ansi-color-names-vector")[1]
    assert vector.count("#") == 16


def test_emacs_survives_a_hostile_name(gruvbox):
    gruvbox.name = HOSTILE_NAME
    read_sexps(emit_theme(gruvbox, "emacs"))     # raises if malformed


# -- vscode and its forks -------------------------------------------------

# Every workbench colour key used by a theme Microsoft ships with VS Code.
# VS Code ignores keys it does not recognise, so a typo would silently do
# nothing; membership here is what proves a key is real.
VSCODE_SHIPPED_COLORS = {
    "activityBar.background", "activityBar.foreground",
    "activityBarBadge.background", "agentsChatInput.border",
    "agentsChatInput.focusBorder", "agentsNewSessionButton.border",
    "agentsPanel.border", "badge.background", "badge.foreground",
    "button.background", "debugExceptionWidget.background",
    "debugExceptionWidget.border", "debugToolBar.background",
    "diffEditor.insertedTextBackground", "diffEditor.removedTextBackground",
    "dropdown.background", "dropdown.border", "dropdown.listBackground",
    "editor.background", "editor.findMatchBackground",
    "editor.findMatchHighlightBackground", "editor.foreground",
    "editor.hoverHighlightBackground", "editor.lineHighlightBackground",
    "editor.selectionBackground", "editor.selectionHighlightBackground",
    "editor.wordHighlightBackground", "editor.wordHighlightStrongBackground",
    "editorBracketHighlight.foreground1", "editorBracketHighlight.foreground2",
    "editorBracketHighlight.foreground3", "editorCursor.foreground",
    "editorGroup.border", "editorGroup.dropBackground",
    "editorGroupHeader.tabsBackground", "editorHoverWidget.background",
    "editorHoverWidget.border", "editorIndentGuide.activeBackground",
    "editorIndentGuide.activeBackground1", "editorIndentGuide.background",
    "editorIndentGuide.background1", "editorLineNumber.activeForeground",
    "editorLineNumber.foreground", "editorLink.activeForeground",
    "editorMarkerNavigation.background", "editorMarkerNavigationError.background",
    "editorMarkerNavigationWarning.background", "editorSuggestWidget.background",
    "editorSuggestWidget.border", "editorWhitespace.foreground",
    "editorWidget.background", "errorForeground",
    "extensionButton.prominentBackground",
    "extensionButton.prominentHoverBackground", "focusBorder", "input.background",
    "input.foreground", "input.placeholderForeground", "inputOption.activeBorder",
    "inputValidation.errorBackground", "inputValidation.errorBorder",
    "inputValidation.infoBackground", "inputValidation.infoBorder",
    "inputValidation.warningBackground", "inputValidation.warningBorder",
    "list.activeSelectionBackground", "list.activeSelectionForeground",
    "list.dropBackground", "list.highlightForeground", "list.hoverBackground",
    "list.inactiveSelectionBackground", "menu.background", "menu.foreground",
    "minimap.selectionHighlight", "notebook.cellEditorBackground",
    "panel.background", "panel.border", "panelTitle.activeBorder",
    "panelTitle.activeForeground", "panelTitle.inactiveForeground",
    "peekView.border", "peekViewEditor.background",
    "peekViewEditor.matchHighlightBackground", "peekViewResult.background",
    "peekViewResult.matchHighlightBackground", "peekViewResult.selectionBackground",
    "peekViewTitle.background", "pickerGroup.border", "pickerGroup.foreground",
    "ports.iconRunningProcessForeground", "progressBar.background",
    "quickInputList.focusBackground", "scrollbar.shadow",
    "scrollbarSlider.activeBackground", "scrollbarSlider.background",
    "scrollbarSlider.hoverBackground", "selection.background",
    "settings.focusedRowBackground", "sideBar.background",
    "sideBarSectionHeader.background", "sideBarTitle.foreground",
    "statusBar.background", "statusBar.debuggingBackground", "statusBar.foreground",
    "statusBar.noFolderBackground", "statusBarItem.prominentBackground",
    "statusBarItem.prominentHoverBackground", "statusBarItem.remoteBackground",
    "tab.activeBackground", "tab.activeForeground", "tab.activeModifiedBorder",
    "tab.border", "tab.inactiveBackground", "tab.inactiveForeground",
    "tab.lastPinnedBorder", "terminal.ansiBlack", "terminal.ansiBlue",
    "terminal.ansiBrightBlack", "terminal.ansiBrightBlue",
    "terminal.ansiBrightCyan", "terminal.ansiBrightGreen",
    "terminal.ansiBrightMagenta", "terminal.ansiBrightRed",
    "terminal.ansiBrightWhite", "terminal.ansiBrightYellow", "terminal.ansiCyan",
    "terminal.ansiGreen", "terminal.ansiMagenta", "terminal.ansiRed",
    "terminal.ansiWhite", "terminal.ansiYellow", "terminal.background",
    "terminal.inactiveSelectionBackground", "titleBar.activeBackground",
    "titleBar.inactiveBackground", "walkThrough.embeddedEditorBackground",
    "welcomePage.tileBackground", "widget.shadow",
}


VSCODE_FAMILY = ("vscode", "cursor", "antigravity")


@pytest.fixture
def vscode_theme(gruvbox):
    import json

    return json.loads(emit_theme(gruvbox, "vscode"))


def test_vscode_output_is_valid_json_with_the_expected_shape(vscode_theme):
    assert set(vscode_theme) == {
        "name", "type", "semanticHighlighting", "colors", "tokenColors",
    }
    assert vscode_theme["type"] == "dark"
    assert vscode_theme["colors"]["editor.background"] == "#282828"


def test_every_vscode_colour_key_is_one_vscode_ships(vscode_theme):
    unknown = set(vscode_theme["colors"]) - VSCODE_SHIPPED_COLORS
    assert not unknown, f"keys not used by any shipped theme: {sorted(unknown)}"


@pytest.mark.skipif(
    not Path("/usr/lib/code/extensions").is_dir(),
    reason="no local VS Code installation to cross-check against",
)
def test_the_embedded_key_list_still_matches_the_installed_vscode(vscode_theme):
    """Catches VS Code renaming or dropping a key we rely on."""
    import json as _json
    import re as _re

    live = set()
    for path in Path("/usr/lib/code/extensions").glob("**/themes/*.json"):
        raw = path.read_text()
        raw = _re.sub(r"//[^\n]*", "", raw)
        raw = _re.sub(r",(\s*[}\]])", r"\1", raw)
        try:
            live |= set(_json.loads(raw).get("colors", {}))
        except ValueError:
            continue
    if not live:
        pytest.skip("could not read any shipped theme")
    assert not set(vscode_theme["colors"]) - live


def test_vscode_terminal_colours_cover_the_whole_palette(gruvbox, vscode_theme):
    colors = vscode_theme["colors"]
    assert colors["terminal.ansiBlack"] == gruvbox.ansi[0].hex
    assert colors["terminal.ansiBrightWhite"] == gruvbox.ansi[15].hex
    assert len([k for k in colors if k.startswith("terminal.ansi")]) == 16


def test_vscode_translucent_keys_carry_an_alpha_channel(vscode_theme):
    for key in ("diffEditor.insertedTextBackground", "editor.findMatchBackground"):
        assert len(vscode_theme["colors"][key]) == 9, key


def test_vscode_token_colours_all_have_settings(vscode_theme):
    for token in vscode_theme["tokenColors"]:
        assert token["scope"]
        assert token["settings"]


def test_vscode_light_scheme_is_typed_light(gruvbox):
    import json

    gruvbox.background, gruvbox.foreground = gruvbox.foreground, gruvbox.background
    assert json.loads(emit_theme(gruvbox, "vscode"))["type"] == "light"


@pytest.mark.parametrize("fork", ["cursor", "antigravity"])
def test_forks_produce_a_byte_identical_theme(gruvbox, fork):
    """They are VS Code derivatives; only the install path differs."""
    assert emit_theme(gruvbox, fork) == emit_theme(gruvbox, "vscode")


@pytest.mark.parametrize("target", VSCODE_FAMILY)
def test_each_fork_has_its_own_install_path(target):
    paths = {t: get_editor(t).INSTALL_PATH for t in VSCODE_FAMILY}
    assert len(set(paths.values())) == len(VSCODE_FAMILY)
    assert get_editor(target).FILENAME == "{name}-color-theme.json"


def test_fork_aliases_resolve():
    assert get_editor("code").NAME == "vscode"
    assert get_editor("ag").NAME == "antigravity"


def test_to_all_reports_shared_filenames_instead_of_overwriting(gruvbox, tmp_path, capsys):
    """The VS Code family writes one filename; that must not be silent."""
    from cscx.cli import main

    source = tmp_path / "src.conf"
    source.write_text((FIXTURES / "gruvbox.kitty.conf").read_text())
    out = tmp_path / "out"
    assert main(["convert", str(source), "--to", "all", "-o", str(out),
                 "--name", "Shared"]) == 0

    errors = capsys.readouterr().err
    assert errors.count("shares shared-color-theme.json") == 2
    assert "identical" in errors
    assert "DIFFERENT CONTENT" not in errors
    assert len(list(out.glob("*-color-theme.json"))) == 1
