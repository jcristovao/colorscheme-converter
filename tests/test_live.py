"""Live preview: OSC sequences that recolour the running terminal."""

from pathlib import Path

import pytest

from cscx import live, parse_file

FIXTURES = Path(__file__).parent / "fixtures"
ESC = "\x1b"
ST = f"{ESC}\\"


@pytest.fixture
def gruvbox():
    return parse_file(FIXTURES / "gruvbox.kitty.conf")


def test_every_palette_slot_gets_an_osc_4(gruvbox):
    payload = live.sequences(gruvbox)
    for index in range(16):
        assert f"{ESC}]4;{index};rgb:" in payload


def test_colours_use_x11_rgb_notation(gruvbox):
    # color1 is #cc241d.
    assert f"{ESC}]4;1;rgb:cc/24/1d{ST}" in live.sequences(gruvbox)


def test_named_colours_use_their_own_osc_codes(gruvbox):
    payload = live.sequences(gruvbox)
    assert f"{ESC}]10;rgb:eb/db/b2{ST}" in payload      # foreground
    assert f"{ESC}]11;rgb:28/28/28{ST}" in payload      # background
    assert f"{ESC}]12;rgb:eb/db/b2{ST}" in payload      # cursor
    assert f"{ESC}]17;rgb:50/49/45{ST}" in payload      # selection


def test_extended_slots_are_included(gruvbox):
    assert gruvbox.indexed
    for index in gruvbox.indexed:
        assert f"{ESC}]4;{index};rgb:" in live.sequences(gruvbox)


def test_unset_values_are_simply_absent():
    """konsole stores no cursor or selection, and inventing one would be wrong."""
    palette = parse_file(FIXTURES / "gruvbox.colorscheme")
    payload = live.sequences(palette)
    assert f"{ESC}]12;" not in payload
    assert f"{ESC}]17;" not in payload
    assert f"{ESC}]4;0;" in payload


def test_reset_restores_palette_and_the_named_colours():
    payload = live.reset_sequences()
    for code in (104, 110, 111, 112):
        assert f"{ESC}]{code}{ST}" in payload


def test_tmux_passthrough_is_used_only_inside_tmux(gruvbox, monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    assert not live.sequences(gruvbox).startswith(f"{ESC}Ptmux;")

    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,123,0")
    wrapped = live.sequences(gruvbox)
    assert wrapped.startswith(f"{ESC}Ptmux;")
    assert wrapped.endswith(ST)
    # tmux needs the inner escapes doubled or it eats them.
    assert f"{ESC}{ESC}]4;0;" in wrapped


def test_support_needs_a_real_terminal(monkeypatch):
    monkeypatch.setenv("TERM", "dumb")
    assert not live.is_supported()
    monkeypatch.delenv("TERM", raising=False)
    assert not live.is_supported()


def test_apply_writes_the_sequences(gruvbox, monkeypatch):
    written: list[str] = []
    monkeypatch.setattr(live, "_write", lambda payload: written.append(payload) or True)

    assert live.apply(gruvbox)
    assert written == [live.sequences(gruvbox)]


def test_apply_reports_failure_rather_than_raising(gruvbox, monkeypatch):
    monkeypatch.setattr(live, "_write", lambda payload: False)
    assert live.apply(gruvbox) is False


def test_previewing_restores_even_when_the_body_raises(gruvbox, monkeypatch):
    written: list[str] = []
    monkeypatch.setattr(live, "_write", lambda payload: written.append(payload) or True)

    with pytest.raises(RuntimeError):
        with live.previewing(gruvbox):
            raise RuntimeError("boom")

    # Leaving someone's terminal recoloured because of an exception would be
    # a rude way to fail.
    assert written[-1] == live.reset_sequences()


def test_previewing_does_not_reset_what_it_could_not_apply(gruvbox, monkeypatch):
    written: list[str] = []

    def refuse(payload: str) -> bool:
        written.append(payload)
        return False

    monkeypatch.setattr(live, "_write", refuse)
    with live.previewing(gruvbox) as applied:
        assert applied is False
    assert len(written) == 1
