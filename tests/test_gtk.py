"""The GTK writers.

Two targets for one toolkit name, because GTK 3 and GTK 4 take overrides by
different mechanisms and neither file does anything for the other's
applications.

The sharpest tests here check the *names*, against the toolkit rather than
against documentation. A misspelled `@define-color` or CSS variable does not
error: GTK parses it, stores it, and nothing ever reads it -- a theme that
loads and silently does nothing, which is the failure this project already
guards against for VS Code and Claude Code.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.color import Color, contrast_ratio, parse_color
from cscx.desktops import get_desktop, scheme_warnings
from cscx.desktops import gtk as gtk_desktop
from cscx.editors import EditorPaletteError

FIXTURES = Path(__file__).parent / "fixtures"
GTK3_LIB = Path("/usr/lib/libgtk-3.so.0")

try:  # GTK's own parser is the best validator available; it is optional.
    import gi  # noqa: F401

    _HAVE_GI = True
except ImportError:
    _HAVE_GI = False

#: Every `@define-color` name GTK 3 declares, extracted from the installed
#: libgtk-3.so. Embedded so the check runs anywhere, and re-extracted by
#: `test_the_embedded_gtk3_names_are_still_current` where the library exists,
#: so the copy cannot go stale -- the same arrangement as VS Code's key list.
GTK3_DECLARED = {
    "app_notification_a", "app_notification_b", "app_notification_border",
    "app_notification_c", "bg_color", "borders", "content_view_bg",
    "error_bg_color", "error_color", "error_fg_color", "info_bg_color",
    "info_fg_color", "insensitive_base_color", "insensitive_bg_color",
    "insensitive_fg_color", "primary_toolbarbutton_text_shadow",
    "question_bg_color", "question_fg_color", "selected_bg_color",
    "selected_fg_color", "success_color", "text_color", "text_view_bg",
    "theme_base_color", "theme_bg_color", "theme_fg_color",
    "theme_selected_bg_color", "theme_selected_fg_color", "theme_text_color",
    "theme_unfocused_base_color", "theme_unfocused_bg_color",
    "theme_unfocused_fg_color", "theme_unfocused_selected_bg_color",
    "theme_unfocused_selected_fg_color", "theme_unfocused_text_color",
    "unfocused_borders", "unfocused_insensitive_color", "warning_bg_color",
    "warning_color", "warning_fg_color", "wm_bg_a", "wm_bg_b", "wm_border",
    "wm_borders_edge", "wm_button_active_color_a", "wm_button_active_color_b",
    "wm_button_active_color_c", "wm_button_hover_color_a",
    "wm_button_hover_color_b", "wm_highlight", "wm_shadow", "wm_title",
    "wm_unfocused_title",
}

#: libadwaita derives these from the matching background colour, by an Oklab
#: transform. Overriding a background is the documented way to set an app-wide
#: accent; writing the standalone colour as well fights that derivation.
DERIVED = {
    "accent-color", "destructive-color", "success-color", "warning-color",
    "error-color", "border-color",
}

#: Translucent overlays in libadwaita, sized to work over any background. A
#: palette holds opaque colours, so writing one here replaces a working
#: overlay with a flat slab.
OVERLAYS = {
    "shade-color", "card-shade-color", "headerbar-shade-color",
    "headerbar-darker-shade-color", "headerbar-border-color",
    "sidebar-shade-color", "sidebar-border-color",
    "secondary-sidebar-shade-color", "secondary-sidebar-border-color",
    "popover-shade-color", "scrollbar-outline-color",
}


def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


def emit(target, palette=None, **kwargs):
    return get_desktop(target).emit(palette or gruvbox(), **kwargs)


def defines(text):
    return dict(re.findall(r"^@define-color\s+(\S+)\s+(#[0-9a-f]{6});$", text, re.M))


def variables(text):
    return dict(re.findall(r"^\s+--([a-z0-9-]+):\s+(#[0-9a-f]{6});$", text, re.M))


# -- names, checked against the toolkit ------------------------------------


def test_every_gtk3_name_is_one_gtk_actually_declares():
    """A misspelled name parses, stores and is never read."""
    names = set(defines(emit("gtk3")))
    assert names, "nothing was written"
    assert names <= GTK3_DECLARED, f"not declared by GTK 3: {names - GTK3_DECLARED}"


@pytest.mark.skipif(not GTK3_LIB.exists(), reason="libgtk-3 not installed")
def test_the_embedded_gtk3_names_are_still_current():
    """Re-extract from the real library so the embedded copy cannot go stale."""
    if not shutil.which("strings"):
        pytest.skip("binutils not installed")
    out = subprocess.run(["strings", str(GTK3_LIB)], capture_output=True,
                         text=True, timeout=120).stdout
    found = set(re.findall(r"@define-color ([a-z_0-9]+)", out))
    assert found, "extracted nothing; the extraction, not GTK, is what broke"
    assert GTK3_DECLARED <= found, f"no longer declared: {GTK3_DECLARED - found}"


def test_gtk3_writes_no_link_colour():
    """GTK 3's Adwaita declares none, so inventing one would be inventing."""
    assert not any("link" in name for name in defines(emit("gtk3")))


def test_gtk4_writes_no_colour_libadwaita_derives_itself():
    written = set(variables(emit("gtk4")))
    assert not written & DERIVED, f"fights libadwaita's own derivation: {written & DERIVED}"


def test_gtk4_writes_no_translucent_overlay():
    written = set(variables(emit("gtk4")))
    assert not written & OVERLAYS, f"opaque colour in an overlay slot: {written & OVERLAYS}"


def test_gtk4_pairs_every_background_with_a_foreground():
    """libadwaita's colours are documented as background/foreground pairs."""
    written = set(variables(emit("gtk4")))
    for name in written:
        if name.endswith("-bg-color"):
            partner = name.replace("-bg-color", "-fg-color")
            assert partner in written, f"{name} written without {partner}"


def test_gtk4_uses_the_root_block_libadwaita_reads():
    output = emit("gtk4")
    assert ":root {" in output and output.rstrip().endswith("}")
    assert "@define-color" not in output, "the compatibility names are inert"


# -- values ----------------------------------------------------------------


@pytest.mark.parametrize("target", ["gtk3", "gtk4"])
def test_every_value_is_an_opaque_hex_colour(target):
    written = defines(emit(target)) or variables(emit(target))
    assert written
    for name, value in written.items():
        parse_color(value)


@pytest.mark.parametrize("target", ["gtk3", "gtk4"])
def test_the_content_surface_is_the_terminal_background_verbatim(target):
    palette = gruvbox()
    written = defines(emit(target, palette)) or variables(emit(target, palette))
    key = "theme_base_color" if target == "gtk3" else "view-bg-color"
    assert written[key] == palette.background.hex


@pytest.mark.parametrize("target", ["gtk3", "gtk4"])
def test_chrome_steps_away_from_the_content_surface(target):
    """Content under chrome under headers, in both polarities."""
    resolved = gtk_desktop.resolve(gruvbox())
    assert resolved.window != resolved.background
    assert resolved.header != resolved.window
    assert resolved.raised != resolved.window


def test_the_semantic_hues_are_written_verbatim():
    written = variables(emit("gtk4"))
    palette = gruvbox()
    assert written["error-bg-color"] == palette.ansi[1].hex
    assert written["destructive-bg-color"] == palette.ansi[1].hex
    assert written["success-bg-color"] == palette.ansi[2].hex
    assert written["warning-bg-color"] == palette.ansi[3].hex


def test_the_accent_foreground_pairs_with_the_accent_actually_used():
    """The regression: an accent that moved needs a foreground chosen for it.

    Gruvbox pairs a cream selection foreground with its #504945 selection.
    That selection cannot carry a focus ring, so the accent falls back to a
    lifted ANSI 4 -- and the cream lands at 2.6:1 on it, where the scheme's
    own background gives 4.1:1. Carrying the foreground across regardless is
    the easy mistake.
    """
    resolved = gtk_desktop.resolve(gruvbox())
    palette = gruvbox()
    assert resolved.accent != palette.selection_background
    assert resolved.accent_fg != palette.selection_foreground
    assert contrast_ratio(resolved.accent_fg, resolved.accent) >= 3.0


def test_a_selection_that_can_carry_the_accent_keeps_its_own_foreground():
    """When the accent really is the selection, the author's pairing stands."""
    palette = gruvbox()
    palette.selection_background = Color(0xE0, 0x60, 0xC0)
    palette.selection_foreground = Color(0x10, 0x10, 0x10)
    resolved = gtk_desktop.resolve(palette)
    assert resolved.accent == palette.selection_background
    assert resolved.accent_fg == palette.selection_foreground


# -- the real parser -------------------------------------------------------

#: Loads a stylesheet through GTK's own CSS parser. A subprocess because GTK 3
#: and GTK 4 cannot be imported into one interpreter.
_CSS_CHECK = """
import sys, gi
gi.require_version("Gtk", sys.argv[1])
from gi.repository import Gtk
errors = []
provider = Gtk.CssProvider()
provider.connect("parsing-error", lambda p, section, err: errors.append(err.message))
try:
    provider.load_from_path(sys.argv[2])
except Exception as exc:            # GTK 3 raises where GTK 4 signals
    errors.append(str(exc))
print("\\n".join(errors))
"""


def gtk_parse_errors(version, path):
    result = subprocess.run(
        [sys.executable, "-c", _CSS_CHECK, version, str(path)],
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout.strip()


@pytest.mark.skipif(not _HAVE_GI, reason="python-gobject not installed")
@pytest.mark.parametrize("target, version", [("gtk3", "3.0"), ("gtk4", "4.0")])
def test_gtk_itself_parses_what_we_write(target, version, tmp_path):
    """The real parser, which is the standard every other target is held to.

    Worth stating what this does and does not prove. GTK 3 rejects a malformed
    colour outright. GTK 4 catches structural errors and bad values in known
    properties, but resolves *custom* properties lazily, so a nonsense value in
    `--window-bg-color` parses cleanly -- which is why the hex format is
    asserted separately above.
    """
    path = tmp_path / f"{target}.css"
    path.write_text(emit(target))
    assert gtk_parse_errors(version, path) == ""


@pytest.mark.skipif(not _HAVE_GI, reason="python-gobject not installed")
def test_the_parser_check_can_actually_fail(tmp_path):
    """A validator that never fails is a validator that proves nothing."""
    bad = tmp_path / "bad.css"
    bad.write_text("@define-color broken notacolour;\n")
    assert "notacolour" in gtk_parse_errors("3.0", bad)


@pytest.mark.skipif(not _HAVE_GI, reason="python-gobject not installed")
def test_gtk3_rejects_the_gtk4_stylesheet(tmp_path):
    """Why these are two files rather than one.

    GTK 3 has no `:root` pseudo-class, so a combined stylesheet would error
    for every GTK 3 application that loaded it.
    """
    path = tmp_path / "gtk4.css"
    path.write_text(emit("gtk4"))
    assert "pseudo-class" in gtk_parse_errors("3.0", path)


# -- registration and activation -------------------------------------------


@pytest.mark.parametrize("alias, target", [
    ("gtk", "gtk4"), ("gnome", "gtk4"), ("libadwaita", "gtk4"),
    ("adwaita", "gtk4"), ("gtk-4.0", "gtk4"), ("gtk-3.0", "gtk3"),
])
def test_the_aliases_point_where_they_should(alias, target):
    """The bare names mean GTK 4, since a GTK 3 file does nothing for it."""
    assert get_desktop(alias) is get_desktop(target)


def test_the_install_paths_are_the_files_gtk_actually_reads():
    assert get_desktop("gtk3").INSTALL_PATH == "~/.config/gtk-3.0/gtk.css"
    assert get_desktop("gtk4").INSTALL_PATH == "~/.config/gtk-4.0/gtk.css"


def test_the_scratch_filenames_are_distinct():
    """`--to all` writes both into one directory."""
    assert get_desktop("gtk3").FILENAME != get_desktop("gtk4").FILENAME


def test_activation_backs_up_an_existing_override_file(tmp_path, monkeypatch):
    from cscx.activation import plan

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    existing = tmp_path / "gtk-4.0" / "gtk.css"
    existing.parent.mkdir(parents=True)
    existing.write_text("@import 'colors.css';\n")

    step = plan(gruvbox(), "gtk4").steps[0]
    assert step.path == existing
    assert step.edits_existing, "an existing file must be backed up, not clobbered"


def test_the_plasma_bridge_is_reported_when_it_owns_the_file(tmp_path, monkeypatch):
    """kde-gtk-config rewrites gtk.css from the KDE scheme, undoing this."""
    from cscx import activation

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(activation.shutil, "which", lambda _: "/usr/bin/stub")
    generated = tmp_path / "gtk-4.0" / "colors.css"
    generated.parent.mkdir(parents=True)
    generated.write_text("@define-color theme_bg_color #000000;\n")

    warnings = activation.plan(gruvbox(), "gtk4").warnings
    assert any("kde-gtk-config" in w for w in warnings)
    assert any("--for kde" in w for w in warnings)


def test_no_bridge_no_note(tmp_path, monkeypatch):
    from cscx import activation

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(activation.shutil, "which", lambda _: None)
    assert not any(
        "kde-gtk-config" in w for w in activation.plan(gruvbox(), "gtk4").warnings
    )


# -- refusals --------------------------------------------------------------


@pytest.mark.parametrize("target", ["gtk3", "gtk4"])
def test_a_palette_missing_a_hue_is_refused_not_guessed(target, tmp_path):
    source = tmp_path / "partial.conf"
    source.write_text("background #000000\nforeground #ffffff\ncolor1 #ff0000\n")
    palette = parse_file(source, format="kitty")

    with pytest.raises(EditorPaletteError, match="eight normal ANSI colors"):
        emit(target, palette)
    assert scheme_warnings(palette, target) == []


def test_a_low_contrast_scheme_is_reported_once_per_problem(tmp_path):
    source = tmp_path / "washed.conf"
    source.write_text(
        "background #808080\nforeground #8a8a8a\n"
        + "\n".join(f"color{i} #{i * 16:02x}8080" for i in range(16))
    )
    found = scheme_warnings(parse_file(source, format="kitty"), "gtk4")
    assert found and len(found) == len(set(found))
    assert sum(w.startswith("normal text:") for w in found) == 1
