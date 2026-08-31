"""The documentation is checked against the code, not trusted to keep up."""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from cscx import __version__
from cscx.editors import EDITORS
from cscx.emitters import EMITTERS
from cscx.formats import PARSERS

ROOT = Path(__file__).resolve().parent.parent
MAN_PAGE = ROOT / "docs" / "cscx.1"
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"

MAN_TEXT = MAN_PAGE.read_text()
#: Roff escapes a literal hyphen as `\-`; searching for option and format
#: names is far clearer against an unescaped copy.
MAN_PLAIN = MAN_TEXT.replace("\\-", "-")
README_TEXT = README.read_text()
FORMATS = sorted({p.NAME for p in PARSERS.values()})


def test_the_man_page_exists_and_is_installed():
    assert MAN_PAGE.is_file()
    config = tomllib.loads(PYPROJECT.read_text())
    shared = config["tool"]["hatch"]["build"]["targets"]["wheel"]["shared-data"]
    assert shared["docs/cscx.1"] == "share/man/man1/cscx.1"


def test_one_version_everywhere():
    """`cscx --version`, the package metadata and the man page must agree."""
    config = tomllib.loads(PYPROJECT.read_text())
    assert config["project"]["version"] == __version__

    title = re.search(r'^\.TH CSCX 1 "[^"]*" "cscx ([^"]+)"', MAN_TEXT, re.M)
    assert title, "man page has no .TH version"
    assert title.group(1) == __version__


@pytest.mark.skipif(not shutil.which("groff"), reason="groff not installed")
def test_the_man_page_has_no_roff_warnings():
    result = subprocess.run(
        ["groff", "-man", "-Tutf8", "-ww", "-z", str(MAN_PAGE)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr.strip(), result.stderr


@pytest.mark.skipif(not shutil.which("man"), reason="man not installed")
def test_the_man_page_renders():
    result = subprocess.run(
        ["man", "--warnings=all", "-l", str(MAN_PAGE)],
        capture_output=True, text=True, timeout=60,
        env={"MANWIDTH": "80", "PATH": "/usr/bin:/bin", "TERM": "dumb"},
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr.strip(), result.stderr
    # man justifies text, so collapse runs of spaces before matching.
    rendered = " ".join(result.stdout.split())
    assert "convert terminal color schemes" in rendered


@pytest.mark.parametrize("name", FORMATS)
def test_every_format_is_documented(name):
    assert name in MAN_PLAIN, f"{name} missing from the man page"
    assert name in README_TEXT, f"{name} missing from the README"


@pytest.mark.parametrize("name", sorted(EDITORS))
def test_every_editor_is_documented(name):
    assert name in MAN_PLAIN, f"{name} missing from the man page"
    assert name in README_TEXT, f"{name} missing from the README"


@pytest.mark.parametrize("command", ["convert", "parse", "detect", "formats"])
def test_every_command_is_documented(command):
    assert command in MAN_PLAIN
    assert command in README_TEXT


def test_the_man_page_covers_every_cli_option():
    """Catches an option added to the parser but never written up."""
    from cscx.cli import build_parser

    documented = set(re.findall(r"--[a-z-]+", MAN_PLAIN))

    parser = build_parser()
    actions = list(parser._actions)
    for subparsers in (a for a in parser._actions if hasattr(a, "choices") and a.choices):
        for sub in subparsers.choices.values():
            actions.extend(sub._actions)

    for action in actions:
        for option in action.option_strings:
            if option.startswith("--") and option != "--help":
                assert option in documented, f"{option} is undocumented"
