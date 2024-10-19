from __future__ import annotations

import os
from typing import TYPE_CHECKING

from InquirerPy import inquirer
from InquirerPy.validator import PathValidator

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def path_prompt(manager: Manager):
    home_path = "~/" if os.name == "posix" else "C:\\"
    hash_path = inquirer.filepath(
        message="Select the directory to scan",
        default=home_path,
        validate=PathValidator(is_dir=True, message="Input is not a directory"),
    ).execute()
    return hash_path
