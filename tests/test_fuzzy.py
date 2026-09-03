"""Fuzzy matching for the scheme filter."""

import pytest

from cscx.fuzzy import matches, rank, score


def test_an_exact_substring_beats_a_scattered_match():
    """`gruv` should find gruvbox before it finds anything merely containing g,r,u,v."""
    assert score("gruv", "gruvbox") > score("gruv", "generic-run-values")


def test_a_match_at_a_word_start_beats_one_mid_word():
    # Both contain "dark"; only the first starts a word with it.
    assert score("dark", "solarized-dark") > score("dark", "solarizeddark")
    assert score("box", "gruv-box") > score("box", "gruvboxy")


def test_an_earlier_substring_ranks_higher():
    assert score("nord", "nord-light") > score("nord", "some-theme-nord")


def test_adjacent_characters_beat_scattered_ones():
    assert score("abc", "abcxxxx") > score("abc", "axbxcxx")


def test_a_subsequence_matches_even_when_scattered():
    assert matches("b16sulph", "base16-atelier-sulphurpool")
    assert score("b16sulph", "base16-atelier-sulphurpool") is not None


def test_characters_must_appear_in_order():
    assert not matches("cba", "abc")
    assert score("zz", "abc") is None


def test_matching_ignores_case():
    assert matches("GRUV", "gruvbox")
    assert matches("gruv", "GRUVBOX")


def test_an_empty_query_matches_everything():
    assert score("", "anything") == 0
    assert rank("", ["a", "b"], key=str) == ["a", "b"]


def test_rank_orders_best_first():
    names = ["base16-gruvbox-dark-soft", "gruvbox", "aggressive-uv"]
    assert rank("gruv", names, key=str)[0] == "gruvbox"


def test_rank_drops_non_matches():
    assert rank("zzz", ["abc", "def"], key=str) == []


def test_rank_is_stable_for_equal_scores():
    items = ["x-same", "y-same"]
    assert rank("same", items, key=str) == items
