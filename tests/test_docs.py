"""The documentation is checked against the code, not trusted to keep up."""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from cscx import __version__
from cscx.desktops import DESKTOPS
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

#: The prose documentation, README first. The README is the entry point and
#: stays short, so a subject may be written up on one of the pages it links
#: to; "documented" means documented somewhere in this set.
GUIDES = sorted((ROOT / "docs").glob("*.md"))
DOCS_TEXT = README_TEXT + "\n".join(page.read_text() for page in GUIDES)

FORMATS = sorted({p.NAME for p in PARSERS.values()})

#: `[text](target)`, ignoring images and bare autolinks.
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _links(page: Path) -> list[str]:
    return [
        target for target in _LINK.findall(page.read_text())
        if not target.startswith(("http://", "https://", "#"))
    ]


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
    assert name in DOCS_TEXT, f"{name} missing from README.md and docs/"


@pytest.mark.parametrize("name", sorted(EDITORS))
def test_every_editor_is_documented(name):
    assert name in MAN_PLAIN, f"{name} missing from the man page"
    assert name in DOCS_TEXT, f"{name} missing from README.md and docs/"


@pytest.mark.parametrize("name", sorted(DESKTOPS))
def test_every_desktop_is_documented(name):
    assert name in MAN_PLAIN, f"{name} missing from the man page"
    assert name in DOCS_TEXT, f"{name} missing from README.md and docs/"


@pytest.mark.parametrize("command", ["convert", "parse", "detect", "formats"])
def test_every_command_is_documented(command):
    assert command in MAN_PLAIN
    assert command in DOCS_TEXT


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


# -- the prose set holds together -----------------------------------------


def _anchors(page: Path) -> set[str]:
    """GitHub's heading slugs: lowercase, punctuation dropped, spaces hyphened."""
    found = set()
    for heading in re.findall(r"^#{1,6}\s+(.*)$", page.read_text(), re.M):
        text = re.sub(r"[`*_]", "", heading).strip().lower()
        text = re.sub(r"[^\w\s-]", "", text)
        found.add(re.sub(r"\s+", "-", text))
    return found


@pytest.mark.parametrize("page", [README, *GUIDES], ids=lambda p: p.name)
def test_every_link_resolves(page):
    """A split README is only an improvement while the links still work."""
    for target in _links(page):
        path, _, anchor = target.partition("#")
        destination = (page.parent / path).resolve() if path else page
        assert destination.is_file(), f"{page.name}: {target} does not exist"
        if anchor:
            assert anchor in _anchors(destination), \
                f"{page.name}: {target} names no heading in {destination.name}"


def test_every_guide_is_reachable_from_the_readme():
    """A page nothing links to is a page nobody reads."""
    linked = {(README.parent / t.partition("#")[0]).resolve() for t in _links(README)}
    for page in GUIDES:
        assert page.resolve() in linked, f"{page.name} is not linked from the README"


def test_the_readme_stays_an_entry_point():
    """It is the front page, not the manual; detail belongs on a linked page."""
    assert len(README_TEXT.splitlines()) < 250


def _prose_paragraphs(page: Path) -> list[list[str]]:
    """Runs of consecutive plain-prose lines, outside code, tables and lists."""
    paragraphs, current, in_fence = [], [], False
    for line in page.read_text().split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            line = ""
        # headings, tables, list items, indented continuations, raw HTML
        structural = in_fence or not line.strip() or re.match(
            r"^(#{1,6}\s|\||<|\s*([-*+]|\d+\.)\s|\s+\S)", line
        )
        if structural:
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append(current)
    return paragraphs


@pytest.mark.parametrize("page", [README, *GUIDES], ids=lambda p: p.name)
def test_prose_is_not_hard_wrapped(page):
    """One line per paragraph.

    Hard wrapping at 80 columns is a habit from man pages, and it does not
    belong here: GitHub reflows the text anyway, and re-wrapping a paragraph
    after a two-word edit turns a one-word change into a six-line diff.
    """
    for paragraph in _prose_paragraphs(page):
        assert len(paragraph) == 1, (
            f"{page.name}: hard-wrapped paragraph starting {paragraph[0][:60]!r}"
        )
