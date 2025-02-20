from __future__ import annotations

import json
from dataclasses import dataclass
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


class LogInfo(NamedTuple):
    level: int
    style: str


class UpdateLogLevel(StrEnum):
    OFF = "OFF"
    CONSOLE = "CONSOLE"
    ON = "ON"


class UpdateInfo(NamedTuple):
    message: Text
    log_info: LogInfo
    version: Version | None


INFO = LogInfo(20, "")
WARNING = LogInfo(30, "bold_yellow")
ERROR = LogInfo(40, "bold_red")


def check_latest_pypi(logging: Literal["OFF", "CONSOLE", "ON"] = UpdateLogLevel.ON) -> tuple[Version, Version | None]:
    """Get latest version from Pypi.

    Args:
        logging (str, optional): Controls where version information is logged.
            - OFF: Do not log version information.
            - CONSOLE: Log version information to the console.
            - ON: Log version information to both the console and the main log file.

    Returns:
        tuple[Version, Version | None]: current_version, latest_version. Returns None for latest_version if any error occurs
    """

    try:
        with request("GET", PYPI_JSON_URL, timeout=30) as response:
            contents = response.content
    except KeyboardInterrupt:
        raise
    except Exception:
        contents = ""

    update = process_pypi_response(contents)

    if logging == UpdateLogLevel.ON:
        log_with_color(update.message.plain, update.log_info.style, update.log_info.level, show_in_stats=False)
    elif logging == UpdateLogLevel.CONSOLE:
        rich.print(update.message)

    return current_version, update.version


def process_pypi_response(response: bytes | str) -> UpdateInfo:
    if not response:
        error_message = Text("Unable to get latest version information", style=ERROR.style)
        return UpdateInfo(error_message, ERROR, None)

    data: dict[str, dict] = json.loads(response)
    releases = list(data["releases"].keys())
    package_info = PackageInfo.create(releases)
    return get_update_info(package_info)


def get_update_info(package_info: PackageInfo) -> UpdateInfo:
    latest_version = package_info.latest_stable_release
    pre_tag = None

    if package_info.is_prerelease:
        latest_version = package_info.latest_prerelease_match
        pre_tag = package_info.prerelease_tag

    if package_info.is_from_the_future or package_info.is_unreleased or not latest_version:
        msg = Text("You are on an unreleased version, skipping version check", style=WARNING.style)
        UpdateInfo(msg, WARNING, latest_version)

    version_text = Text(str(latest_version), style="cyan")

    if package_info.current_version == latest_version:
        msg_mkp = "You are currently on the latest version of Cyberdrop-DL :white_check_mark:"
        if pre_tag:
            msg_mkp = f"You are currently on the latest {pre_tag} version:"
        msg = Text.from_markup(msg_mkp, style=INFO.style).append_text(version_text)
        UpdateInfo(msg, INFO, latest_version)

    spacer = f"{pre_tag} " if pre_tag else ""
    msg_str = f"A new {spacer}version of Cyberdrop-DL is available: "
    msg = Text(msg_str, style=WARNING.style).append_text(version_text)
    return UpdateInfo(msg, WARNING, latest_version)


def get_prerelease_tag(version: Version) -> str | None:
    if version.is_devrelease:
        return "dev"
    if version.is_prerelease:
        return version.pre[0]  # type: ignore


@dataclass
class PackageInfo:
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
