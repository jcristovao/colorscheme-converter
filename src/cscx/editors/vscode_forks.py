"""Cursor and Antigravity: VS Code forks that read the same theme format.

Both are VS Code derivatives and consume a byte-identical color theme; what
differs is only where the extension lives, and which registry it came from
(both use Open VSX rather than the Visual Studio Marketplace). Rather than
copy the writer, these delegate to it and carry their own install path, so
`cscx formats` can tell you where the file belongs.

Neither is installed on the machine this was developed on, so unlike VS Code
their install paths follow the documented fork convention -- `~/.<app>/
extensions` -- rather than being read off a local installation.
"""

from __future__ import annotations

from ..palette import Palette
from . import vscode
from .roles import CONTRAST_TARGET

__all__ = ["CURSOR", "ANTIGRAVITY"]


class _VSCodeFork:
    """A target whose theme file is exactly VS Code's, stored elsewhere."""

    EXTENSION = vscode.EXTENSION
    FILENAME = vscode.FILENAME
    BINARY = vscode.BINARY

    def __init__(self, name: str, install_path: str) -> None:
        self.NAME = name
        self.INSTALL_PATH = install_path

    def emit(
        self,
        palette: Palette,
        *,
        terminal_exact: bool = False,
        contrast_target: float | None = None,
    ) -> str:
        return vscode.emit(
            palette, terminal_exact=terminal_exact, contrast_target=contrast_target
        )


CURSOR = _VSCodeFork(
    "cursor", "~/.cursor/extensions/<extension>/themes/{name}-color-theme.json"
)
ANTIGRAVITY = _VSCodeFork(
    "antigravity",
    "~/.antigravity/extensions/<extension>/themes/{name}-color-theme.json",
)
