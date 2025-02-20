from __future__ import annotations

import json
from enum import StrEnum
from functools import cached_property
from typing import Literal, NamedTuple, Self

import rich
from packaging.version import Version
from requests import request
from rich.text import Text

from cyberdrop_dl import __version__
from cyberdrop_dl.utils.logger import log_with_color

PYPI_JSON_URL = "https://pypi.org/pypi/cyberdrop-dl-patched/json"
current_version = Version(__version__)


class UpdateLogLevel(StrEnum):
    OFF = "OFF"
    CONSOLE = "CONSOLE"
    ON = "ON"


class UpdateDetails(NamedTuple):
    message: Text
    log_level: int
    color: str
    version: Version | None


def check_latest_pypi(logging: Literal["OFF", "CONSOLE", "ON"] = UpdateLogLevel.ON) -> tuple[str, Version | None]:
    """Checks if the current version is the latest version.

    Args:
        logging (str, optional): Controls where version information is logged.
            - OFF: Do not log version information.
            - CONSOLE: Log version information to the console.
            - ON: Log version information to both the console and the main log file.

    Returns:
        tuple[str, str | None]: current_version, latest_version. Returns None for latest_version if any error occurs
    """

    try:
        with request("GET", PYPI_JSON_URL, timeout=30) as response:
            contents = response.content
    except KeyboardInterrupt:
        raise
    except Exception:
        contents = ""

    update_info = process_pypi_response(contents)

    if logging == UpdateLogLevel.ON:
        log_with_color(update_info.message.plain, update_info.color, update_info.log_level, show_in_stats=False)
    elif logging == UpdateLogLevel.CONSOLE:
        rich.print(update_info.message)

    return __version__, update_info.version


def process_pypi_response(response: bytes | str) -> UpdateDetails:
    if not response:
        color = "bold_red"
        prerelease_message = Text("Unable to get latest version information", style=color)
        level = 40
        return UpdateDetails(prerelease_message, level, color, None)

    data: dict[str, dict] = json.loads(response)

    releases = list(data["releases"].keys())
    color = ""
    level = 30
    package_info = PackageDetails.create(releases)
    prerelease_msg, level = get_prerelease_message(package_info)
    latest_version = package_info.latest_version
    message = prerelease_msg
    if not message:
        latest_version = package_info.latest_stable_release
        message, level = get_stable_release_message(package_info)

    return UpdateDetails(message, level, color, latest_version)


class PackageDetails(NamedTuple):
    current_version: Version
    releases: list[Version]

    @cached_property
    def latest_version(self) -> Version:
        return max(self.releases)

    @cached_property
    def latest_non_prerelease_version(self) -> Version:
        return max(self.releases)

    @cached_property
    def latest_prerelease_version(self) -> Version:
        return max(self.prereleases)

    @cached_property
    def prerelease_tag(self) -> str | None:
        return get_prerelease_tag(self.current_version)

    @cached_property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease_tag)

    @cached_property
    def prereleases(self) -> list[Version]:
        return [r for r in self.releases if get_prerelease_tag(r)]

    @cached_property
    def stable_releases(self) -> list[Version]:
        return [r for r in self.releases if not get_prerelease_tag(r)]

    @cached_property
    def latest_stable_release(self) -> Version:
        return max(self.stable_releases)

    @cached_property
    def latest_prerelease_match(self) -> Version | None:
        matches = [r for r in self.prereleases if get_prerelease_tag(r) == self.prerelease_tag]
        if matches:
            return max(matches)

    @cached_property
    def is_unreleased(self) -> bool:
        return self.current_version not in self.releases

    @cached_property
    def is_from_the_future(self) -> bool:
        # Faster to compute than is_unreleased
        return self.current_version > self.latest_version

    @classmethod
    def create(cls, releases: list[str]) -> Self:
        all_releases = [Version(release) for release in releases]
        return cls(current_version, all_releases)


def get_stable_release_message(package_info: PackageDetails) -> tuple[Text, int]:
    assert not package_info.is_prerelease

    if package_info.is_unreleased:
        color = "bold_yellow"
        return Text("You are on an unreleased version, skipping version check", style=color), 30

    info = Text(str(package_info.latest_stable_release), style="cyan")

    if package_info.current_version == package_info.latest_stable_release:
        message_mkp = "You are currently on the latest version of Cyberdrop-DL :white_check_mark:"
        return Text.from_markup(message_mkp).append_text(info), 20

    message_str = "A new version of Cyberdrop-DL is available: "
    return Text(message_str).append_text(info), 30


def get_prerelease_message(package_info: PackageDetails) -> tuple[Text | None, int]:
    if not package_info.is_prerelease:
        return None, 10

    if package_info.is_from_the_future or package_info.is_unreleased or not package_info.latest_prerelease_match:
        return Text("You are on an unreleased version, skipping version check", style="bold_yellow"), 30

    info = Text(str(package_info.latest_prerelease_match), style="cyan")

    if package_info.current_version == package_info.latest_prerelease_match:
        message_mkp = f"You are currently on the latest {package_info.prerelease_tag} version:"
        return Text.from_markup(message_mkp).append_text(info), 20

    message_str = f"A new {package_info.prerelease_tag} version of Cyberdrop-DL is available: "
    return Text(message_str).append_text(info), 30


def get_prerelease_tag(version: Version) -> str | None:
    if version.is_prerelease:
        return version.pre[0]  # type: ignore
    if version.is_devrelease:
        return "dev"
