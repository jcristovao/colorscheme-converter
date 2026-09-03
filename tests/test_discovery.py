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


# -- source labelling -----------------------------------------------------


def test_a_location_names_its_source(tmp_path):
    from cscx.discovery import SearchLocation

    assert SearchLocation("kitty themes", tmp_path, ("*",)).source == "kitty"
    assert SearchLocation("X resources", tmp_path, ("*",),
                          source="xresources").source == "xresources"


def test_discovered_schemes_carry_their_source(fixture_location):
    for entry in discover(locations=[fixture_location]):
        assert entry.source == "fixtures"


def test_the_source_is_not_the_storage_format(tmp_path):
    """Neovim schemes are cached as kitty files; calling them kitty misleads."""
    from cscx.discovery import SearchLocation

    (tmp_path / "nord.conf").write_text(
        (FIXTURES / "gruvbox.kitty.conf").read_text()
    )
    location = SearchLocation("neovim colorschemes", tmp_path, ("*.conf",),
                              "kitty", source="neovim")
    entry = discover(locations=[location])[0]
    assert entry.format == "kitty"
    assert entry.source == "neovim"


def test_the_haystack_covers_everything_worth_matching(fixture_location):
    entry = discover(locations=[fixture_location])[0]
    for part in (entry.name, entry.source, entry.format, entry.origin):
        assert part in entry.haystack


# -- filtering ------------------------------------------------------------


@pytest.fixture
def catalogue():
    from cscx.discovery import Discovered

    return [
        Discovered(Path("/a/gruvbox.conf"), "kitty", 0.9, "neovim colorschemes", "neovim"),
        Discovered(Path("/b/gruvbox-dark.toml"), "alacritty", 0.9, "alacritty themes", "alacritty"),
        Discovered(Path("/c/nord.colorscheme"), "konsole", 0.9, "konsole schemes", "konsole"),
        Discovered(Path("/d/base16-atelier-sulphurpool.conf"), "kitty", 0.9,
                   "neovim colorschemes", "neovim"),
    ]


def test_a_bare_query_is_matched_fuzzily(catalogue):
    from cscx.discovery import filter_schemes

    hits = filter_schemes("b16sulph", catalogue)
    assert [h.path.stem for h in hits] == ["base16-atelier-sulphurpool"]


def test_a_bare_query_also_matches_the_source(catalogue):
    from cscx.discovery import filter_schemes

    assert len(filter_schemes("neovim", catalogue)) == 2


def test_a_source_constraint_narrows_exactly(catalogue):
    from cscx.discovery import filter_schemes

    assert len(filter_schemes("source:konsole", catalogue)) == 1
    assert len(filter_schemes("src:neovim", catalogue)) == 2


def test_a_format_constraint_is_separate_from_the_source(catalogue):
    from cscx.discovery import filter_schemes

    # Two entries are kitty-format, but they came from neovim.
    assert len(filter_schemes("format:kitty", catalogue)) == 2
    assert len(filter_schemes("fmt:alacritty", catalogue)) == 1


def test_constraints_and_fuzzy_text_combine(catalogue):
    from cscx.discovery import filter_schemes

    hits = filter_schemes("source:neovim gruv", catalogue)
    assert [h.path.stem for h in hits] == ["gruvbox"]


def test_every_bare_term_must_match(catalogue):
    from cscx.discovery import filter_schemes

    assert filter_schemes("gruv nord", catalogue) == []
    assert len(filter_schemes("gruv dark", catalogue)) == 1


def test_an_unknown_prefix_is_treated_as_text(catalogue):
    from cscx.discovery import filter_schemes

    assert filter_schemes("colour:red", catalogue) == []


def test_an_empty_query_keeps_everything(catalogue):
    from cscx.discovery import filter_schemes

    assert filter_schemes("", catalogue) == catalogue
