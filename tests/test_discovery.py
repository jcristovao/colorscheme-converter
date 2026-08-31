"""Discovery: finding the schemes already on the machine."""

from pathlib import Path

import pytest

from cscx.discovery import (
    Discovered,
    SearchLocation,
    discover,
    installed_applications,
    search_locations,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_location():
    return SearchLocation("fixtures", FIXTURES, ("*",), None)


def test_finds_every_fixture(fixture_location):
    found = discover(locations=[fixture_location])
    names = {d.path.name for d in found}
    assert "gruvbox.kitty.conf" in names
    assert "gruvbox.colorscheme" in names
    assert "gruvbox.itermcolors" in names


def test_each_fixture_is_identified_correctly(fixture_location):
    by_name = {d.path.name: d.format for d in discover(locations=[fixture_location])}
    assert by_name["gruvbox.kitty.conf"] == "kitty"
    assert by_name["gruvbox.colorscheme"] == "konsole"
    assert by_name["gruvbox.foot.ini"] == "foot"
    assert by_name["gruvbox.wezterm.toml"] == "wezterm"


def test_an_expected_format_breaks_ties(tmp_path):
    """`.toml` is shared, so the directory's own expectation should decide."""
    (tmp_path / "theme.toml").write_text(
        (FIXTURES / "gruvbox.alacritty.toml").read_text()
    )
    location = SearchLocation("alacritty themes", tmp_path, ("*.toml",), "alacritty")
    found = discover(locations=[location])
    assert [d.format for d in found] == ["alacritty"]


def test_unrelated_files_are_ignored(tmp_path):
    (tmp_path / "notes.txt").write_text("just some prose, no colors here\n")
    (tmp_path / "empty.conf").write_text("")
    assert discover(locations=[SearchLocation("x", tmp_path, ("*",))]) == []


def test_oversized_files_are_skipped_without_reading(tmp_path):
    from cscx.discovery import MAX_SIZE

    big = tmp_path / "huge.conf"
    big.write_text("color0 #282828\n" + "# padding\n" * (MAX_SIZE // 10))
    assert big.stat().st_size > MAX_SIZE
    assert discover(locations=[SearchLocation("x", tmp_path, ("*",))]) == []


def test_missing_directories_are_not_an_error(tmp_path):
    location = SearchLocation("nope", tmp_path / "does-not-exist", ("*",))
    assert discover(locations=[location]) == []


def test_extra_paths_accept_a_file_or_a_directory():
    single = discover([FIXTURES / "gruvbox.kitty.conf"], locations=[])
    assert [d.format for d in single] == ["kitty"]

    directory = discover([FIXTURES], locations=[])
    assert len(directory) >= 10


def test_results_are_deduplicated_by_resolved_path(fixture_location):
    found = discover([FIXTURES], locations=[fixture_location])
    paths = [d.path for d in found]
    assert len(paths) == len(set(paths))


def test_results_are_sorted_by_format_then_name(fixture_location):
    found = discover(locations=[fixture_location])
    assert [d.key for d in found] == sorted(d.key for d in found)


def test_display_name_is_readable():
    entry = Discovered(Path("/x/gruvbox_material_dark.toml"), "alacritty", 0.9, "test")
    assert entry.name == "gruvbox material dark"


def test_search_locations_are_well_formed():
    for location in search_locations():
        assert location.label and location.patterns
        assert isinstance(location.root, Path)


def test_installed_applications_reports_a_subset_of_what_we_support():
    from cscx.editors import EDITORS
    from cscx.emitters import EMITTERS

    known = set(EMITTERS) | set(EDITORS)
    assert installed_applications() <= known
