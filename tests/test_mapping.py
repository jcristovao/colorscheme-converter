"""The optional override file for the tunable half of the editor mapping."""

import tomllib
from pathlib import Path

import pytest

from cscx import parse_file
from cscx.color import contrast_ratio
from cscx.editors.roles import derive
from cscx.mapping import (
    ACCENT_ROLES,
    DEFAULT,
    RAMP_KEYS,
    MappingError,
    config_path,
    dump,
    load,
    reset_cache,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def clean_cache():
    reset_cache()
    yield
    reset_cache()


@pytest.fixture
def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "mapping.toml"
    path.write_text(text)
    return path


# -- nothing is required --------------------------------------------------


def test_with_no_file_the_defaults_apply(tmp_path):
    assert load(tmp_path / "absent.toml", use_cache=False) == DEFAULT


def test_nothing_is_ever_written(tmp_path, monkeypatch):
    """cscx creates no config of its own; activate is the only writer."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    load(use_cache=False)
    dump()
    assert not (tmp_path / "cscx").exists()


def test_the_file_lives_under_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "cscx/mapping.toml"


# -- merging --------------------------------------------------------------


def test_an_override_replaces_only_what_it_names(tmp_path):
    result = load(write(tmp_path, "[roles]\nbase08 = 4\n"), use_cache=False)
    assert result.accents["base08"] == 4
    assert result.accents["base0D"] == DEFAULT.accents["base0D"]
    assert result.ramp == DEFAULT.ramp
    assert result.comment_contrast == DEFAULT.comment_contrast


def test_ramp_and_scalars_merge_independently(tmp_path):
    result = load(
        write(tmp_path, "[ramp]\nbase02 = 0.35\ncomment_contrast = 7.0\n"),
        use_cache=False,
    )
    assert result.ramp["base02"] == 0.35
    assert result.ramp["base01"] == DEFAULT.ramp["base01"]
    assert result.comment_contrast == 7.0
    assert result.comment_ceiling == DEFAULT.comment_ceiling


def test_an_empty_file_changes_nothing(tmp_path):
    assert load(write(tmp_path, ""), use_cache=False) == DEFAULT


# -- validation is loud ---------------------------------------------------


def test_an_unknown_section_is_refused(tmp_path):
    with pytest.raises(MappingError, match="unknown section"):
        load(write(tmp_path, "[colours]\nred = 1\n"), use_cache=False)


def test_an_unknown_role_is_refused(tmp_path):
    """Quietly ignoring it would leave someone staring at an unchanged theme."""
    with pytest.raises(MappingError, match="not an accent role"):
        load(write(tmp_path, "[roles]\nbase0Z = 4\n"), use_cache=False)


def test_a_non_accent_role_is_refused(tmp_path):
    """base00 and base05 come from the palette; base01-04 are the ramp."""
    for role in ("base00", "base03", "base05"):
        with pytest.raises(MappingError, match="not an accent role"):
            load(write(tmp_path, f"[roles]\n{role} = 4\n"), use_cache=False)


@pytest.mark.parametrize("value", ["16", "-1", '"red"', "true", "1.5"])
def test_a_bad_slot_is_refused(tmp_path, value):
    with pytest.raises(MappingError, match="ANSI slot 0-15"):
        load(write(tmp_path, f"[roles]\nbase08 = {value}\n"), use_cache=False)


def test_an_unknown_ramp_key_is_refused(tmp_path):
    with pytest.raises(MappingError, match="unknown"):
        load(write(tmp_path, "[ramp]\nbase99 = 0.5\n"), use_cache=False)


@pytest.mark.parametrize("value", ["1.5", "-0.2"])
def test_a_ramp_fraction_outside_zero_to_one_is_refused(tmp_path, value):
    with pytest.raises(MappingError, match="fraction"):
        load(write(tmp_path, f"[ramp]\nbase02 = {value}\n"), use_cache=False)


def test_an_impossible_contrast_ratio_is_refused(tmp_path):
    with pytest.raises(MappingError, match="1 to 21"):
        load(write(tmp_path, "[ramp]\ncomment_contrast = 40\n"), use_cache=False)


def test_a_floor_above_the_ceiling_is_refused(tmp_path):
    """It would leave the comment search no range to move in."""
    with pytest.raises(MappingError, match="no range to search"):
        load(
            write(tmp_path, "[ramp]\ncomment_floor = 0.9\ncomment_ceiling = 0.5\n"),
            use_cache=False,
        )


def test_invalid_toml_says_so(tmp_path):
    with pytest.raises(MappingError, match="not valid TOML"):
        load(write(tmp_path, "[roles\n"), use_cache=False)


# -- effect on the output -------------------------------------------------


def test_an_accent_override_changes_the_generated_role(tmp_path, gruvbox):
    mapping = load(write(tmp_path, "[roles]\nbase08 = 4\n"), use_cache=False)
    roles = derive(gruvbox, mapping=mapping)
    assert roles["base08"] == gruvbox.ansi[4]
    assert roles.provenance["base08"] == "color4"


def test_a_blended_role_can_be_pinned_to_a_slot(tmp_path, gruvbox):
    """base09 and base0F are blends by default; an override takes a real slot."""
    default = derive(gruvbox)
    assert default.provenance["base0F"].startswith("25%")

    mapping = load(write(tmp_path, "[roles]\nbase0F = 14\n"), use_cache=False)
    roles = derive(gruvbox, mapping=mapping)
    assert roles["base0F"] == gruvbox.ansi[14]
    assert roles.provenance["base0F"] == "color14"


def test_a_ramp_override_moves_the_shade(tmp_path, gruvbox):
    mapping = load(write(tmp_path, "[ramp]\nbase02 = 0.35\n"), use_cache=False)
    assert derive(gruvbox, mapping=mapping)["base02"] != derive(gruvbox)["base02"]


def test_a_contrast_override_is_honoured(tmp_path, gruvbox):
    mapping = load(write(tmp_path, "[ramp]\ncomment_contrast = 7.0\n"), use_cache=False)
    roles = derive(gruvbox, mapping=mapping)
    assert contrast_ratio(roles["base03"], roles["base00"]) >= 7.0


def test_an_explicit_argument_still_wins_over_the_file(tmp_path, gruvbox):
    """--contrast on the command line beats the config, as a flag should."""
    mapping = load(write(tmp_path, "[ramp]\ncomment_contrast = 7.0\n"), use_cache=False)
    roles = derive(gruvbox, mapping=mapping, contrast_target=1.0)
    assert contrast_ratio(roles["base03"], roles["base00"]) < 7.0


def test_terminal_exact_still_respects_an_accent_override(tmp_path, gruvbox):
    mapping = load(write(tmp_path, "[roles]\nbase08 = 4\n"), use_cache=False)
    roles = derive(gruvbox, terminal_exact=True, mapping=mapping)
    assert roles["base08"] == gruvbox.ansi[4]


# -- dump -----------------------------------------------------------------


def test_the_dump_is_valid_toml_and_reloads_unchanged(tmp_path):
    text = dump(DEFAULT)
    assert tomllib.loads(text)
    assert load(write(tmp_path, text), use_cache=False) == DEFAULT


def test_the_dump_covers_every_knob():
    text = dump(DEFAULT)
    for role in ACCENT_ROLES:
        assert role in text
    for key in RAMP_KEYS:
        assert key in text
    for scalar in ("comment_contrast", "comment_floor", "comment_ceiling"):
        assert scalar in text


def test_the_dump_marks_the_blended_roles_rather_than_inventing_a_slot():
    text = dump(DEFAULT)
    assert "# base09 = <slot>" in text
    assert "# base0F = <slot>" in text


# -- caching --------------------------------------------------------------


def test_the_default_load_is_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "cscx").mkdir()
    (tmp_path / "cscx/mapping.toml").write_text("[roles]\nbase08 = 4\n")

    assert load().accents["base08"] == 4
    (tmp_path / "cscx/mapping.toml").write_text("[roles]\nbase08 = 2\n")
    assert load().accents["base08"] == 4, "should have been cached"

    reset_cache()
    assert load().accents["base08"] == 2
