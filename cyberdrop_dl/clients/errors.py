from __future__ import annotations

import contextlib
from functools import singledispatch
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.utils.constants import VALIDATION_ERROR_FOOTER

if TYPE_CHECKING:
    from requests import Response
    from yaml.constructor import ConstructorError

    from cyberdrop_dl.scraper.crawler import ScrapeItem
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


class CDLBaseError(Exception):
    """Base exception for cyberdrop-dl errors."""

    def __init__(
        self,
        ui_message: str = "Something went wrong",
        *,
        message: str | None = None,
        status: str | int | None = None,
        origin: ScrapeItem | MediaItem | URL | Path | None = None,
    ) -> None:
        self.ui_message = ui_message
        self.message = message or ui_message
        self.origin = origin
        if origin and not isinstance(origin, URL | Path):
            self.origin = origin.parents[0] if origin.parents else None
        super().__init__(self.message)
        if status:
            self.status = status
            super().__init__(self.status)


class InvalidContentTypeError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when the content type isn't as expected."""
        ui_message = "Invalid Content Type"
        super().__init__(ui_message, message=message, origin=origin)


class NoExtensionError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when no extension is given for a file."""
        ui_message = "No File Extension"
        super().__init__(ui_message, message=message, origin=origin)


class PasswordProtectedError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when a file is password protected."""
        ui_message = "Password Protected"
        msg = message or "File/Folder is password protected"
        super().__init__(ui_message, message=msg, origin=origin)


class MaxChildrenError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when an scrape item reaches its max number or children."""
        ui_message = "Max Children Reached"
        msg = message or "Max number of children reached"
        super().__init__(ui_message, message=msg, origin=origin)


class DDOSGuardError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when DDoS-Guard is detected."""
        ui_message = "DDoS-Guard"
        msg = message or "DDoS-Guard detected"
        super().__init__(ui_message, message=msg, origin=origin)


class DownloadError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None
    ) -> None:
        """This error will be thrown when a download fails."""
        ui_message = create_error_msg(status)
        msg = message
        super().__init__(ui_message, message=msg, status=status, origin=origin)


class SlowDownloadError(DownloadError):
    def __init__(self, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when a file will be skipped do to a low download speed."""
        ui_message = "Slow Download"
        super().__init__(ui_message, origin=origin)


class InsufficientFreeSpaceError(CDLBaseError):
    def __init__(self, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when no enough storage is available."""
        ui_message = "Insufficient Free Space"
        super().__init__(ui_message, origin=origin)


class RestrictedFiletypeError(CDLBaseError):
    def __init__(self, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when has a filytpe not allowed by config."""
        ui_message = "Restricted Filetype"
        super().__init__(ui_message, origin=origin)


class MediaFireError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None
    ) -> None:
        """This error will be thrown when a scrape fails."""
        ui_message = f"{status} MediaFire Error"
        super().__init__(ui_message, message=message, status=status, origin=origin)


class RealDebridError(CDLBaseError):
    """Base RealDebrid API error."""

    def __init__(self, response: Response, code: int, message: str) -> None:
        url = URL(response.url)
        self.path = url.path
        msg = message.capitalize()
        ui_message = f"{code} RealDebrid Error"
        super().__init__(ui_message, message=msg, status=code, origin=url)


class ScrapeError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None
    ) -> None:
        """This error will be thrown when a scrape fails."""
        ui_message = create_error_msg(status)
        msg = message
        super().__init__(ui_message, message=msg, status=status, origin=origin)


class LoginError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when the login fails for a site."""
        ui_message = "Failed Login"
        super().__init__(ui_message, message=message, origin=origin)


class JDownloaderError(CDLBaseError):
    """This error will be thrown for any Jdownloader error."""


class InvalidYamlError(CDLBaseError):
    def __init__(self, file: Path, e: ConstructorError) -> None:
        """This error will be thrown when a yaml config file has invalid values."""
        mark = e.problem_mark if hasattr(e, "problem_mark") else e
        message = f"File '{file.resolve()}' has an invalid config. Please verify and edit it manually\n {mark}\n\n{VALIDATION_ERROR_FOOTER}"
        super().__init__("Invalid YAML", message=message, origin=file)


@singledispatch
def create_error_msg(error: int) -> str:
    with contextlib.suppress(ValueError):
        msg = HTTPStatus(error).phrase
        return f"{error} {msg}"
    return f"{error} HTTP Error"


@create_error_msg.register
def _(error: str) -> str:
    return error
