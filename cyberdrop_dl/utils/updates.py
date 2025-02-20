from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

import rich
from requests import request
from rich.text import Text

from cyberdrop_dl import __version__ as current_version
from cyberdrop_dl.utils.logger import log_with_color

PYPI_JSON_URL = "https://pypi.org/pypi/cyberdrop-dl-patched/json"
PRELEASE_VERSION_PATTERN = r"(\d+)\.(\d+)\.(\d+)(?:\.([a-z]+)\d+|([a-z]+)\d+)"
PRERELEASE_TAGS = {
    "dev": "Development",
    "pre": "Pre-Release",
    "rc": "Release Candidate",
    "a": "Alpha",
    "b": "Beta",
}


class UpdatesLogLevel(StrEnum):
    OFF = "OFF"
    CONSOLE = "CONSOLE"
    ON = "ON"


def check_latest_pypi(logging: Literal["OFF", "CONSOLE", "ON"] = UpdatesLogLevel.ON) -> tuple[str, str]:
    """Checks if the current version is the latest version.

    Args:
        log_to (str, optional): Controls where version information is logged.
            - OFF: Do not log version information.
            - CONSOLE: Log version information to the console.
            - ON: Log version information to both the console and the main log file.

    Returns:
        tuple[str, str]: A tuple containing the current version and the latest
        available version.
    """

    try:
        with request("GET", PYPI_JSON_URL, timeout=30) as response:
            contents = response.content
    except Exception:
        color = "bold_red"
        message = Text("Unable to get latest version information", style=color)
        if logging == UpdatesLogLevel.CONSOLE:
            rich.print(message)
        elif logging == UpdatesLogLevel.ON:
            log_with_color(message.plain, color, 40, show_in_stats=False)
        return "", ""

    data: dict[str, dict] = json.loads(contents)
    latest_version: str = data["info"]["version"]
    releases = list(data["releases"].keys())
    color = ""
    level = 30
    is_prerelease, latest_testing_version, message = check_prerelease_version(releases)

    if current_version not in releases:
        message = Text("You are on an unreleased version, skipping version check")
        color = "bold_yellow"
    elif is_prerelease:
        latest_version = latest_testing_version
        color = "bold_red"
    elif current_version != latest_version:
        message_mkup = f"A new version of Cyberdrop-DL is available: [cyan]{latest_version}[/cyan]"
        message = Text.from_markup(message_mkup)
    else:
        message = Text.from_markup("You are currently on the latest version of Cyberdrop-DL :white_check_mark:")
        level = 20

    if logging == UpdatesLogLevel.CONSOLE:
        rich.print(message)
    elif logging == UpdatesLogLevel.ON:
        log_with_color(message.plain, color, level, show_in_stats=False)

    return current_version, latest_version


def check_prerelease_version(releases: list[str]) -> tuple[bool, str, Text]:
    """Checks if the current version is a prerelease

    Args:
        releases (list[str]): List of releases from pypi

    Returns:
        tuple[bool, str, Text]: running_prerelease, latest_prerelease_version, release_info_message
    """
    match = re.match(PRELEASE_VERSION_PATTERN, current_version)
    latest_testing_version = ""
    message = Text("")
    running_prerelease = next((tag for tag in PRERELEASE_TAGS if tag in current_version), False)

    if running_prerelease and match:
        major_version, minor_version, patch_version, dot_tag, no_dot_tag = match.groups()
        test_tag = dot_tag if dot_tag else no_dot_tag
        regex_str = rf"{major_version}\.{minor_version}\.{patch_version}(\.{test_tag}\d+|{test_tag}\d+)"
        rough_matches = [release for release in releases if re.match(regex_str, release)]
        latest_testing_version = max(rough_matches, key=lambda x: int(re.search(r"(\d+)$", x).group()))  # type: ignore
        ui_tag = PRERELEASE_TAGS.get(test_tag, "Testing").lower()

        if current_version != latest_testing_version:
            message = f"A new {ui_tag} version of Cyberdrop-DL is available: "
            message = Text(message).append_text(Text(latest_testing_version, style="cyan"))
        else:
            message = f"You are currently on the latest {ui_tag} version of [b cyan]{major_version}.{minor_version}.{patch_version}[/b cyan]"
            message = Text.from_markup(message)
    return bool(running_prerelease), latest_testing_version, message
