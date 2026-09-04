"""Install a scheme into an application's configuration, persistently.

This is the only part of cscx that edits files you did not ask it to create,
so it is built to be inspected before it runs and undone after it does:

  plan  ->  back up  ->  apply  ->  validate  ->  roll back on failure

Every plan is a plain data structure, so `cscx activate --dry-run` prints
exactly what would change without touching anything. Edits are anchored to a
marker comment, so activating twice rewrites one line rather than appending a
second copy. Where a format can be machine-checked -- alacritty's TOML, foot's
own `--check-config`, kitty's own loader -- the result is validated and the
backup restored if the application would have rejected it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .editors import EDITORS, get_editor
from .editors._common import slug
from .emitters import get_emitter
from .palette import Palette

__all__ = [
    "Plan",
    "Step",
    "ActivationError",
    "ACTIVATABLE",
    "plan",
    "apply_plan",
    "MARKER",
]

#: Anchors the line cscx owns. Activating again rewrites the line below it
#: rather than appending a second include.
MARKER = "# cscx: managed line, rewritten on each activation"


class ActivationError(Exception):
    """Raised when a plan cannot be built or safely applied."""


@dataclass(frozen=True, slots=True)
class Step:
    """One file to create or rewrite."""

    path: Path
    content: str | bytes
    description: str
    #: True when the file already exists and will therefore be backed up.
    edits_existing: bool = False
    #: True for the step that writes the scheme itself, as opposed to the
    #: config edit that points at it. Callers that only want to place a theme
    #: -- `cscx browse`'s copy -- need to find it without matching on prose.
    is_theme: bool = False

    def diff_summary(self) -> str:
        verb = "edit" if self.edits_existing else "create"
        return f"{verb:7} {self.path}  ({self.description})"


@dataclass
class Plan:
    """Everything an activation would do, before any of it happens."""

    app: str
    steps: list[Step] = field(default_factory=list)
    #: How to make the application notice, in words.
    reload: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def theme_path(self) -> Path | None:
        """Where the scheme itself goes, ignoring any config edit."""
        for step in self.steps:
            if step.is_theme:
                return step.path
        return None

    def describe(self) -> str:
        lines = [f"{self.app}:"]
        lines += [f"  {step.diff_summary()}" for step in self.steps]
        if self.reload:
            lines.append(f"  reload:  {self.reload}")
        lines += [f"  note:    {warning}" for warning in self.warnings]
        return "\n".join(lines)


# -- helpers --------------------------------------------------------------


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


def _managed_line(text: str, directive: str) -> str:
    """Insert or rewrite the single line cscx owns, anchored to `MARKER`."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == MARKER:
            if index + 1 < len(lines):
                lines[index + 1] = directive
            else:
                lines.append(directive)
            return "\n".join(lines) + "\n"

    prefix = text if text.endswith("\n") or not text else text + "\n"
    return f"{prefix}\n{MARKER}\n{directive}\n"


def _expand(template: str) -> Path:
    """Expand an install path, honouring XDG overrides.

    The editor writers spell their install paths as `~/.config/...` because
    that is what their own documentation says, but a user who has moved
    XDG_CONFIG_HOME means it for every application.
    """
    if template.startswith("~/.config/"):
        return _config_home() / template[len("~/.config/"):]
    if template.startswith("~/.local/share/"):
        return _data_home() / template[len("~/.local/share/"):]
    return Path(template).expanduser()


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


# -- terminal activators --------------------------------------------------


def _kitty(palette: Palette, name: str) -> Plan:
    config = _config_home() / "kitty/kitty.conf"
    theme = _config_home() / f"kitty/themes/{name}.conf"
    body = get_emitter("kitty").emit(palette, None)

    return Plan(
        app="kitty",
        steps=[
            Step(theme, body, "the theme itself", is_theme=True),
            Step(config, _managed_line(_read(config), f"include themes/{name}.conf"),
                 "include the theme", config.exists()),
        ],
        reload="kitten @ load-config, or ctrl+shift+f5 in kitty",
    )


def _alacritty(palette: Palette, name: str) -> Plan:
    config = _config_home() / "alacritty/alacritty.toml"
    theme = _config_home() / f"alacritty/themes/{name}.toml"
    body = get_emitter("alacritty").emit(palette, None)

    return Plan(
        app="alacritty",
        steps=[
            Step(theme, body, "the theme itself", is_theme=True),
            Step(config, _alacritty_import(_read(config), theme),
                 "import the theme", config.exists()),
        ],
        reload="none needed; alacritty watches its config",
    )


def _alacritty_import(text: str, theme: Path) -> str:
    """Set `general.import`, respecting TOML's one-table-per-name rule.

    A marker comment cannot be used here: `import` has to sit inside the
    `[general]` table, and appending a second `[general]` would make the file
    invalid TOML rather than merely wrong.
    """
    directive = f'import = ["{theme}"]'
    lines = text.splitlines()

    general = next(
        (i for i, line in enumerate(lines) if line.strip() == "[general]"), None
    )
    if general is None:
        prefix = text if text.endswith("\n") or not text else text + "\n"
        return f"{prefix}\n[general]\n{directive}\n"

    # Replace the first `import` line belonging to this table.
    for index in range(general + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("["):
            break
        if stripped.startswith("import"):
            lines[index] = directive
            return "\n".join(lines) + "\n"

    lines.insert(general + 1, directive)
    return "\n".join(lines) + "\n"


def _foot(palette: Palette, name: str) -> Plan:
    config = _config_home() / "foot/foot.ini"
    theme = _config_home() / f"foot/themes/{name}.ini"
    body = get_emitter("foot").emit(palette, None)

    # foot requires an absolute path, or one starting with `~/`.
    return Plan(
        app="foot",
        steps=[
            Step(theme, body, "the theme itself", is_theme=True),
            Step(config, _managed_line(_read(config), f"include={theme}"),
                 "include the theme", config.exists()),
        ],
        reload="restart foot, or reload it from its config menu",
    )


def _ghostty(palette: Palette, name: str) -> Plan:
    config = _config_home() / "ghostty/config"
    theme = _config_home() / f"ghostty/themes/{name}"
    body = get_emitter("ghostty").emit(palette, None)

    return Plan(
        app="ghostty",
        steps=[
            Step(theme, body, "the theme itself", is_theme=True),
            Step(config, _managed_line(_read(config), f"theme = {name}"),
                 "select the theme", config.exists()),
        ],
        reload="ctrl+shift+, in ghostty, or restart it",
    )


def _konsole(palette: Palette, name: str, profile: Path | None = None) -> Plan:
    scheme = _data_home() / f"konsole/{name}.colorscheme"
    body = get_emitter("konsole").emit(palette, None)
    steps = [Step(scheme, body, "the colour scheme", is_theme=True)]
    warnings: list[str] = []

    if profile is not None:
        steps.append(
            Step(profile, _konsole_profile(_read(profile), name),
                 "point the profile at it", profile.exists())
        )
        reload = "reopen konsole tabs, or reselect the profile"
    else:
        warnings.append(
            "no profile given, so the scheme is installed but not selected; "
            "pass --profile, or pick it in Settings > Edit Current Profile > Appearance"
        )
        reload = "select the scheme in konsole's profile settings"

    return Plan(app="konsole", steps=steps, reload=reload, warnings=warnings)


def _konsole_profile(text: str, name: str) -> str:
    """Set `ColorScheme` inside `[Appearance]`, adding the section if absent."""
    lines = text.splitlines()
    directive = f"ColorScheme={name}"

    section = next(
        (i for i, line in enumerate(lines) if line.strip() == "[Appearance]"), None
    )
    if section is None:
        prefix = text if text.endswith("\n") or not text else text + "\n"
        return f"{prefix}\n[Appearance]\n{directive}\n"

    for index in range(section + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("["):
            lines.insert(index, directive)
            return "\n".join(lines) + "\n"
        if stripped.startswith("ColorScheme="):
            lines[index] = directive
            return "\n".join(lines) + "\n"

    lines.append(directive)
    return "\n".join(lines) + "\n"


# -- editor activators ----------------------------------------------------
#
# These only place a file where the editor already looks, so there is no
# config to edit and nothing to back up. Telling the editor to *use* it stays
# a deliberate act -- `:colorscheme name` -- rather than something cscx does
# to your init file behind your back.


#: How to make each editor use a theme once the file is in place. Saying it
#: is deliberate: cscx will not edit an init file to select a colorscheme.
_RELOAD = {
    "vim": ":colorscheme {name}",
    "neovim": ":colorscheme {name}",
    "helix": 'theme = "{name}" in ~/.config/helix/config.toml',
    "emacs": "(load-theme '{name} t)",
    "claude-code": '/theme, or "theme": "custom:{name}" in ~/.claude/settings.json',
}


def _editor(app: str) -> object:
    def build(palette: Palette, name: str) -> Plan:
        editor = get_editor(app)
        target = _expand(editor.INSTALL_PATH.format(name=name))

        if app in {"vscode", "cursor", "antigravity"}:
            return _vscode_extension(palette, name, app)

        return Plan(
            app=app,
            steps=[Step(target, editor.emit(palette), "the theme itself", is_theme=True)],
            reload=_RELOAD[app].format(name=name),
        )

    return build


#: Where each VS Code fork keeps its extensions.
_EXTENSION_ROOTS = {
    "vscode": Path("~/.vscode/extensions"),
    "cursor": Path("~/.cursor/extensions"),
    "antigravity": Path("~/.antigravity/extensions"),
}


def _vscode_extension(palette: Palette, name: str, app: str) -> Plan:
    """A theme document alone is not loadable; write the wrapper too."""
    import json

    from .color import is_dark

    root = _EXTENSION_ROOTS[app].expanduser() / f"cscx.{name}"
    body = get_editor(app).emit(palette)
    dark = palette.background is None or is_dark(palette.background)

    manifest = {
        "name": f"cscx-{name}",
        "displayName": f"{palette.name or name} (cscx)",
        "version": "1.0.0",
        "engines": {"vscode": "*"},
        "categories": ["Themes"],
        "contributes": {
            "themes": [{
                "label": palette.name or name,
                "uiTheme": "vs-dark" if dark else "vs",
                "path": f"./themes/{name}-color-theme.json",
            }]
        },
    }

    return Plan(
        app=app,
        steps=[
            Step(root / "package.json", json.dumps(manifest, indent=2) + "\n",
                 "the extension manifest"),
            Step(root / "themes" / f"{name}-color-theme.json", body,
                 "the theme itself", is_theme=True),
        ],
        reload=f"restart {app}, then pick “{palette.name or name}” in the theme picker",
    )


ACTIVATABLE: dict[str, object] = {
    "kitty": _kitty,
    "alacritty": _alacritty,
    "foot": _foot,
    "ghostty": _ghostty,
    "konsole": _konsole,
    **{app: _editor(app) for app in sorted(EDITORS)},
}


def plan(
    palette: Palette,
    app: str,
    *,
    name: str | None = None,
    profile: Path | None = None,
) -> Plan:
    """Work out what activating `palette` for `app` would change."""
    if app not in ACTIVATABLE:
        raise ActivationError(
            f"cannot activate for {app!r}; known: {', '.join(sorted(ACTIVATABLE))}"
        )
    theme_name = slug(name or palette.name)
    builder = ACTIVATABLE[app]
    if app == "konsole":
        return builder(palette, theme_name, profile)      # type: ignore[operator]
    return builder(palette, theme_name)                   # type: ignore[operator]


# -- applying -------------------------------------------------------------


def apply_plan(plan: Plan, *, backup: bool = True, validate: bool = True) -> list[Path]:
    """Carry out `plan`, returning the backups taken.

    On a validation failure every backup is restored and the original error
    re-raised, so a rejected config never survives the call.
    """
    backups: dict[Path, Path] = {}
    created: list[Path] = []

    try:
        for step in plan.steps:
            step.path.parent.mkdir(parents=True, exist_ok=True)
            if step.path.exists():
                if backup:
                    backups[step.path] = _back_up(step.path)
            else:
                created.append(step.path)
            if isinstance(step.content, bytes):
                step.path.write_bytes(step.content)
            else:
                step.path.write_text(step.content)

        if validate and (problems := _validate(plan)):
            raise ActivationError("; ".join(problems))
    except Exception:
        _roll_back(backups, created)
        raise

    return list(backups.values())


def _back_up(path: Path) -> Path:
    """Copy `path` aside, never overwriting an earlier backup.

    The timestamp is only second-resolution, so two activations inside the
    same second would otherwise collide and destroy the older copy -- which
    is precisely the one holding the untouched original.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.cscx-{stamp}.bak")
    counter = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.cscx-{stamp}-{counter}.bak")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def _roll_back(backups: dict[Path, Path], created: list[Path]) -> None:
    for original, backup in backups.items():
        try:
            shutil.copy2(backup, original)
        except OSError:
            continue
    for path in created:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _validate(plan: Plan) -> list[str]:
    """Ask the application itself whether it would accept the result."""
    problems: list[str] = []
    for step in plan.steps:
        checker = _CHECKERS.get(plan.app)
        if checker is None:
            continue
        if (problem := checker(step.path)) is not None:
            problems.append(problem)
    return problems


def _check_toml(path: Path) -> str | None:
    if path.suffix != ".toml":
        return None
    try:
        tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return f"{path} is not valid TOML: {exc}"
    return None


def _check_foot(path: Path) -> str | None:
    if path.suffix != ".ini" or not shutil.which("foot"):
        return None
    result = subprocess.run(
        ["foot", "--check-config", "-c", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    errors = [
        line for line in result.stderr.splitlines()
        if " err: " in line and "deprecated" not in line
    ]
    return f"foot rejected {path}: {errors[0]}" if errors else None


def _check_kitty(path: Path) -> str | None:
    if path.suffix != ".conf" or not shutil.which("kitty"):
        return None
    result = subprocess.run(
        ["kitty", "+runpy",
         f"from kitty.config import load_config; load_config({str(path)!r})"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        detail = (result.stderr.strip().splitlines() or ["unknown error"])[-1]
        return f"kitty rejected {path}: {detail}"
    return None


_CHECKERS = {
    "alacritty": _check_toml,
    "foot": _check_foot,
    "kitty": _check_kitty,
}
