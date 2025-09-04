from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import rich

_TEXT_EDITORS = "micro", "nano", "vim"  # Ordered by preference
_USING_SSH = "SSH_CONNECTION" in os.environ
_USING_DESKTOP_ENVIROMENT = any(var in os.environ for var in ("DISPLAY", "WAYLAND_DISPLAY"))
_CUSTOM_EDITOR = os.environ.get("EDITOR")


def open_in_text_editor(file_path: Path) -> bool | None:
    """Opens file in OS text editor."""

    if _CUSTOM_EDITOR:
        path = shutil.which(_CUSTOM_EDITOR)
        if not path:
            msg = f"Editor '{_CUSTOM_EDITOR}' from env bar $EDITOR is not available"
            raise ValueError(msg)
        cmd = path, file_path

    elif platform.system() == "Darwin":
        cmd = "open", "-a", "TextEdit", file_path

    elif platform.system() == "Windows":
        cmd = "notepad.exe", file_path

    elif _USING_DESKTOP_ENVIROMENT and not _USING_SSH and _xdg_set_default_if_none(file_path):
        cmd = "xdg-open", file_path

    elif fallback_editor := _find_text_editor():
        cmd = fallback_editor, file_path
    else:
        msg = "No default text editor found"
        raise ValueError(msg)

    bin_path, *rest = cmd
    if Path(bin_path).stem == "micro":
        cmd = bin_path, "-keymenu", "true", *rest

    rich.print(f"Opening '{file_path}' with '{bin_path}'...")
    subprocess.call(cmd, stderr=subprocess.DEVNULL)


@lru_cache
def _find_text_editor() -> str | None:
    for editor in _TEXT_EDITORS:
        if bin_path := shutil.which(editor):
            return bin_path


@lru_cache
def _xdg_set_default_if_none(file: Path) -> bool:
    """
    Ensures a file's MIME type has a default XDG app, falling back to whatever app is currently set for 'text/plain'

    Required to open YAML files as most of the time they have no default

    Returns `True` if a default app is now associated, `False` if setting the default failed
    """

    def xdg_mime_query(arg: str, *args: str) -> str:
        cmd = "xdg-mime", "query", arg, *args
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return process.stdout.strip()

    mimetype = xdg_mime_query("filetype", str(file))
    if not mimetype:
        return False

    has_default = xdg_mime_query("default", mimetype)
    if has_default:
        return True

    default_text_app = xdg_mime_query("default", "text/plain")
    if not default_text_app:
        return False

    return subprocess.call(["xdg-mime", "default", default_text_app, mimetype]) == 0
