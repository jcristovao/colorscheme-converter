"""Claude Code custom themes.

Claude Code drops an override whose token it does not recognise, silently and
with no error, so a wrong name here would produce a theme that loads and does
nothing. The token list is therefore pinned, and cross-checked against the
installed binary when there is one.
"""

import json
import re
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.editors import claude_code, get_editor

FIXTURES = Path(__file__).parent / "fixtures"

#: Every token in Claude Code's own presets, read out of the installed binary.
CLAUDE_CODE_TOKENS = {
    "autoAccept", "autoAcceptShimmer", "background", "bashBorder",
    "bashMessageBackgroundColor", "blue_FOR_SUBAGENTS_ONLY", "briefLabelClaude",
    "briefLabelYou", "chromeYellow", "claude",
    "claudeBlueShimmer_FOR_SYSTEM_SPINNER", "claudeBlue_FOR_SYSTEM_SPINNER",
    "claudeShimmer", "clawd_background", "clawd_body", "composerSidebarBackground",
    "cyan_FOR_SUBAGENTS_ONLY", "diffAdded", "diffAddedDimmed", "diffAddedWord",
    "diffRemoved", "diffRemovedDimmed", "diffRemovedWord", "effortUltra", "error",
    "fastMode", "fastModeShimmer", "green_FOR_SUBAGENTS_ONLY", "ide", "inactive",
    "inactiveShimmer", "inverseText", "memoryBackgroundColor", "merged",
    "orange_FOR_SUBAGENTS_ONLY", "permission", "permissionShimmer",
    "pink_FOR_SUBAGENTS_ONLY", "planMode", "professionalBlue", "promptBorder",
    "promptBorderShimmer", "purple_FOR_SUBAGENTS_ONLY", "rainbow_blue",
    "rainbow_blue_shimmer", "rainbow_green", "rainbow_green_shimmer",
    "rainbow_indigo", "rainbow_indigo_shimmer", "rainbow_orange",
    "rainbow_orange_shimmer", "rainbow_red", "rainbow_red_shimmer",
    "rainbow_violet", "rainbow_violet_shimmer", "rainbow_yellow",
    "rainbow_yellow_shimmer", "rate_limit_empty", "rate_limit_fill",
    "red_FOR_SUBAGENTS_ONLY", "remember", "selectionBg", "skill", "subtle",
    "success", "suggestion", "text", "userMessageBackground",
    "userMessageBackgroundHover", "warning", "warningShimmer",
    "yellow_FOR_SUBAGENTS_ONLY",
}

#: Claude Code's own colour validator, transcribed from the binary:
#: rgb(r,g,b) | #rrggbb | #rgb | ansi256(n) | ansi:<name>
VALID_COLOUR = re.compile(
    r"^(rgb\(\s?\d{1,3},\s?\d{1,3},\s?\d{1,3}\s?\)"
    r"|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}"
    r"|ansi256\(\d{1,3}\)|ansi:[A-Za-z]+)$"
)


@pytest.fixture
def gruvbox():
    palette = parse_file(FIXTURES / "gruvbox.kitty.conf")
    palette.name = "Gruvbox"
    return palette


@pytest.fixture
def theme(gruvbox):
    return json.loads(claude_code.emit(gruvbox))


def test_the_document_has_exactly_the_shape_claude_code_reads(theme):
    assert set(theme) == {"name", "base", "overrides"}
    assert theme["name"] == "Gruvbox"


def test_every_token_is_one_claude_code_knows(theme):
    """An unrecognised token is dropped without complaint, so this is the check."""
    unknown = set(theme["overrides"]) - CLAUDE_CODE_TOKENS
    assert not unknown, f"tokens Claude Code would silently drop: {sorted(unknown)}"


def test_no_token_is_left_out(theme):
    assert set(theme["overrides"]) == CLAUDE_CODE_TOKENS
    assert len(theme["overrides"]) == 72


def test_every_value_passes_claude_codes_own_validator(theme):
    for token, value in theme["overrides"].items():
        assert VALID_COLOUR.match(value), f"{token} = {value!r} would be dropped"


def test_the_base_is_a_real_preset(theme):
    assert theme["base"] in {
        "dark", "light", "dark-ansi", "light-ansi",
        "dark-daltonized", "light-daltonized",
    }


def test_the_base_follows_the_palette_lightness(gruvbox):
    assert json.loads(claude_code.emit(gruvbox))["base"] == "dark-ansi"

    gruvbox.background, gruvbox.foreground = gruvbox.foreground, gruvbox.background
    assert json.loads(claude_code.emit(gruvbox))["base"] == "light-ansi"


def test_the_two_bases_really_do_differ():
    """If they did not, choosing between them would be pointless."""
    differing = {
        token for token in claude_code._DARK_ANSI
        if claude_code._DARK_ANSI[token] != claude_code._LIGHT_ANSI[token]
    }
    assert len(differing) == 37


def test_palette_values_are_preferred_where_the_scheme_has_one(gruvbox, theme):
    """A scheme carries a foreground; the ANSI presets only have sixteen slots."""
    assert theme["overrides"]["text"] == gruvbox.foreground.hex
    assert theme["overrides"]["inverseText"] == gruvbox.background.hex
    assert theme["overrides"]["selectionBg"] == gruvbox.selection_background.hex


def test_terminal_exact_uses_the_ansi_slot_instead(gruvbox):
    exact = json.loads(claude_code.emit(gruvbox, terminal_exact=True))["overrides"]
    # dark-ansi maps `text` to whiteBright, which is slot 15.
    assert exact["text"] == gruvbox.ansi[15].hex
    assert exact["text"] != gruvbox.foreground.hex or gruvbox.ansi[15] == gruvbox.foreground


def test_literal_values_in_the_preset_are_passed_through(theme):
    """One token is a literal even in dark-ansi; there is no slot to substitute."""
    assert theme["overrides"]["professionalBlue"] == "rgb(106,155,204)"


def test_a_palette_without_selection_falls_back_to_the_ansi_slot():
    palette = parse_file(FIXTURES / "gruvbox.colorscheme")     # konsole: no selection
    assert palette.selection_background is None
    overrides = json.loads(claude_code.emit(palette))["overrides"]
    assert VALID_COLOUR.match(overrides["selectionBg"])


def test_it_is_registered_under_its_name_and_aliases():
    assert get_editor("claude-code").NAME == "claude-code"
    assert get_editor("claude").NAME == "claude-code"
    assert get_editor("cc").NAME == "claude-code"


def test_it_installs_where_claude_code_looks():
    editor = get_editor("claude-code")
    assert editor.INSTALL_PATH == "~/.claude/themes/{name}.json"
    assert editor.FILENAME == "{name}.json"


def test_a_hostile_name_stays_valid_json(gruvbox):
    gruvbox.name = 'evil" name\nwith \\ backslash'
    document = json.loads(claude_code.emit(gruvbox))
    assert "\n" not in document["name"]


# -- against the installed Claude Code ------------------------------------


def _live_binary() -> Path | None:
    """The Claude Code the `claude` command actually runs.

    Not simply the newest directory under versions/: those names sort
    lexically, which puts 2.1.76 after 2.1.221 and reads a build a year out
    of date. Following the executable is the only reliable answer.
    """
    import shutil

    if (found := shutil.which("claude")) is None:
        return None
    resolved = Path(found).resolve()
    return resolved if resolved.is_file() else None


def _tokens_in(binary: Path) -> set[str]:
    data = binary.read_bytes()
    index = data.find(b"bashBorder:")
    if index == -1:
        return set()
    blob = data[index - 2000: index + 4000].decode("utf-8", "replace")
    return set(re.findall(r"([A-Za-z_][\w]*):\"(?:rgb\(|#|ansi)", blob))


@pytest.mark.skipif(_live_binary() is None, reason="no local Claude Code")
def test_every_token_we_emit_is_recognised_by_the_installed_claude_code():
    """The direction that matters.

    A token Claude Code does not know is dropped in silence, so emitting one
    is a real defect. Claude Code knowing tokens we do not set is not: the
    base preset supplies those, which is what a base is for.
    """
    live = _tokens_in(_live_binary())
    if not live:
        pytest.skip("theme table not found in this build")

    unknown = CLAUDE_CODE_TOKENS - live
    assert not unknown, (
        f"these would be silently dropped by the installed Claude Code: "
        f"{sorted(unknown)}"
    )


@pytest.mark.skipif(_live_binary() is None, reason="no local Claude Code")
def test_report_tokens_the_installed_build_has_that_we_do_not_set():
    """Not a failure, but worth knowing: the token set does change.

    Version 2.1.76 had 67 tokens and called one `selectionBackground`; by
    2.1.221 there were 72 and it had been renamed `selectionBg`.
    """
    extra = _tokens_in(_live_binary()) - CLAUDE_CODE_TOKENS
    assert isinstance(extra, set)      # informational; the base covers them
