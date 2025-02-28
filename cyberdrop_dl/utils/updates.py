from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Literal, NamedTuple, Self

import rich
from packaging.version import Version
from requests import request
from rich.text import Text

from cyberdrop_dl import __version__
from cyberdrop_dl.utils.logger import log_with_color

if TYPE_CHECKING:
    from collections.abc import Iterable

PYPI_JSON_URL = "https://pypi.org/pypi/cyberdrop-dl-patched/json"
current_version = Version(__version__)


class LogInfo(NamedTuple):
    level: int
    style: str


class UpdateInfo(NamedTuple):
    message: Text
    log_info: LogInfo
    version: Version | None


INFO = LogInfo(20, "")
WARNING = LogInfo(30, "yellow")
ERROR = LogInfo(40, "bold_red")


ERROR_TEXT = Text("Unable to get latest version information", style=ERROR.style)
ERROR_UPDATE_INFO = UpdateInfo(ERROR_TEXT, ERROR, None)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
@dataclass(order=True)
class PackageInfo:
    current_version: Version
    releases: tuple[Version, ...]

    @cached_property
    def latest(self) -> Version:
        return max(self.releases)

    @cached_property
    def latest_prerelease(self) -> Version:
        return max(self.prereleases)

    @cached_property
    def prerelease_tag(self) -> str | None:
        return get_prerelease_tag(self.current_version)

    @cached_property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease_tag)

    @cached_property
    def prereleases(self) -> tuple[Version, ...]:
        return tuple([r for r in self.releases if get_prerelease_tag(r)])

    @cached_property
    def stable_releases(self) -> tuple[Version, ...]:
        return tuple([r for r in self.releases if not get_prerelease_tag(r)])

    @cached_property
    def latest_stable(self) -> Version:
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
        # Faster to compute than is_unreleased if self.latest is already cached
        return self.current_version > self.latest

    @classmethod
    def create(cls, releases: Iterable[str]) -> Self:
        all_releases = tuple([Version(r) for r in releases])
        return cls(current_version, all_releases)


#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def check_latest_pypi(logging: Literal["OFF", "CONSOLE", "ON"] = "ON") -> tuple[Version, Version | None]:
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

    if logging == "ON":
        log_with_color(update.message.plain, update.log_info.style, update.log_info.level, show_in_stats=False)
    elif logging == "CONSOLE":
        rich.print(update.message)

    return current_version, update.version


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def process_pypi_response(response: bytes | str) -> UpdateInfo:
    if not response:
        return ERROR_UPDATE_INFO

    try:
        data: dict[str, dict] = json.loads(response)
        releases = data["releases"].keys()
        package_info = PackageInfo.create(releases)
    except Exception:
        return ERROR_UPDATE_INFO
    return get_update_info(package_info)


def get_update_info(package_info: PackageInfo) -> UpdateInfo:
    latest_version = package_info.latest_stable
    pre_tag = None

    if package_info.is_prerelease:
        latest_version = package_info.latest_prerelease_match
        pre_tag = package_info.prerelease_tag

    if package_info.is_from_the_future or package_info.is_unreleased or not latest_version:
        msg = Text("You are on an unreleased version, skipping version check", style=WARNING.style)
        if pre_tag:
            msg = msg.append_text(get_latest_stable_msg(package_info))
        return UpdateInfo(msg, WARNING, latest_version)

    if package_info.current_version >= latest_version:
        msg, log_level = get_using_latest_msg(package_info, latest_version)
        if pre_tag and package_info.latest > package_info.current_version:
            msg = msg.append_text(get_latest_stable_msg(package_info))
        return UpdateInfo(msg, log_level, latest_version)

    version_text = Text(str(latest_version), style="cyan")
    spacer = f"{pre_tag} " if pre_tag else ""
    msg_str = f"A new {spacer}version of Cyberdrop-DL is available: "
    msg = Text(msg_str, style=WARNING.style).append_text(version_text)
    return UpdateInfo(msg, WARNING, latest_version)


def get_latest_stable_msg(package_info: PackageInfo) -> Text:
    msg_mkp = "\n\nLatest stable version of Cyberdrop-DL: "
    version_text = Text(str(package_info.latest_stable), style="cyan")
    return Text.from_markup(msg_mkp).append_text(version_text)


def get_using_latest_msg(package_info: PackageInfo, latest_version: Version) -> tuple[Text, LogInfo]:
    msg_mkp = "You are currently on the latest version of Cyberdrop-DL :white_check_mark:"

    if not package_info.prerelease_tag:
        return Text.from_markup(msg_mkp, style=INFO.style), INFO

    latest_text = Text(str(latest_version), style="cyan")
    msg_mkp = f"You are currently on the latest {package_info.prerelease_tag} version: "
    if package_info.latest_prerelease <= package_info.current_version:
        return Text.from_markup(msg_mkp, style=INFO.style).append_text(latest_text), INFO

    new_tag = get_prerelease_tag(package_info.latest_prerelease)
    msg1 = Text.from_markup(msg_mkp, style=WARNING.style).append_text(latest_text)
    msg_mkp2 = f" but a newer prerelease version of type {new_tag} is available: "
    latest_prerelease_text = Text(str(package_info.latest_prerelease), style="cyan")
    msg2 = Text.from_markup(msg_mkp2, style=WARNING.style).append_text(latest_prerelease_text)
    return msg1.append_text(msg2), WARNING


def get_prerelease_tag(version: Version) -> str | None:
    if version.is_devrelease:
        return "dev"
    if version.is_prerelease:
        return version.pre[0]  # type: ignore
