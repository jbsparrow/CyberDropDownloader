from __future__ import annotations

from functools import singledispatch
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from yaml import YAMLError
from yarl import URL

from cyberdrop_dl.utils.constants import VALIDATION_ERROR_FOOTER

if TYPE_CHECKING:
    from requests import Response

    from cyberdrop_dl.scraper.crawler import ScrapeItem
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


# See: https://developers.cloudflare.com/support/troubleshooting/cloudflare-errors/troubleshooting-cloudflare-5xx-errors/
CLOUDFLARE_ERRORS = {
    520: "Unexpected Response",
    521: "Web Server Down",
    522: "Connection Timeout",
    523: "Origin Is Unreachable",
    524: "Response Timeout",
    525: "SSL Handshake Failed",
    526: "Untrusted",
    530: "IP Banned / Restricted",
}


class CDLBaseError(Exception):
    """Base exception for cyberdrop-dl errors."""

    def __init__(
        self,
        ui_failure: str = "Something went wrong",
        *,
        message: str | None = None,
        status: str | int | None = None,
        origin: ScrapeItem | MediaItem | URL | Path | None = None,
    ) -> None:
        self.ui_failure = ui_failure
        self.message = message or ui_failure
        self.origin = get_origin(origin)
        super().__init__(self.message)
        if status:
            self.status = status
            super().__init__(self.status)

    def __str__(self) -> str:
        if self.ui_failure == self.message:
            return self.message
        return f"{self.ui_failure} - {self.message}"


class InvalidContentTypeError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when the content type isn't as expected."""
        ui_failure = "Invalid Content Type"
        super().__init__(ui_failure, message=message, origin=origin)


class NoExtensionError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when no extension is given for a file."""
        ui_failure = "No File Extension"
        super().__init__(ui_failure, message=message, origin=origin)


class InvalidExtensionError(NoExtensionError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when no extension is given for a file."""
        super().__init__(message=message, origin=origin)
        self.ui_failure = "Invalid File Extension"


class PasswordProtectedError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when a file is password protected."""
        ui_failure = "Password Protected"
        msg = message or "File/Folder is password protected"
        super().__init__(ui_failure, message=msg, origin=origin)


class MaxChildrenError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when an scrape item reaches its max number or children."""
        ui_failure = "Max Children Reached"
        msg = message or "Max number of children reached"
        super().__init__(ui_failure, message=msg, origin=origin)


class DDOSGuardError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when DDoS-Guard is detected."""
        ui_failure = "DDoS-Guard"
        msg = message or "DDoS-Guard detected"
        super().__init__(ui_failure, message=msg, origin=origin)


class DownloadError(CDLBaseError):
    def __init__(
        self,
        status: str | int,
        message: str | None = None,
        origin: ScrapeItem | MediaItem | URL | None = None,
        retry: bool = False,
    ) -> None:
        """This error will be thrown when a download fails."""
        ui_failure = create_error_msg(status)
        msg = message
        self.retry = retry
        super().__init__(ui_failure, message=msg, status=status, origin=origin)


class SlowDownloadError(DownloadError):
    def __init__(self, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when a file will be skipped do to a low download speed."""
        ui_failure = "Slow Download"
        super().__init__(ui_failure, origin=origin)


class InsufficientFreeSpaceError(CDLBaseError):
    def __init__(self, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when no enough storage is available."""
        ui_failure = "Insufficient Free Space"
        super().__init__(ui_failure, origin=origin)


class RestrictedFiletypeError(CDLBaseError):
    def __init__(self, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when has a filytpe not allowed by config."""
        ui_failure = "Restricted Filetype"
        super().__init__(ui_failure, origin=origin)


class DurationError(CDLBaseError):
    def __init__(self, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """THis error will be thrown when the file duration is not allowed by the config."""
        ui_failure = "Duration Not Allowed"
        super().__init__(ui_failure, origin=origin)


class MediaFireError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None
    ) -> None:
        """This error will be thrown when a scrape fails."""
        ui_failure = f"{status} MediaFire Error"
        super().__init__(ui_failure, message=message, status=status, origin=origin)


class RealDebridError(CDLBaseError):
    """Base RealDebrid API error."""

    def __init__(self, response: Response, code: int, message: str) -> None:
        url = URL(response.url)
        self.path = url.path
        msg = message.capitalize()
        ui_failure = f"{code} RealDebrid Error"
        super().__init__(ui_failure, message=msg, status=code, origin=url)


class ScrapeError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None
    ) -> None:
        """This error will be thrown when a scrape fails."""
        ui_failure = create_error_msg(status)
        super().__init__(ui_failure, message=message, status=status, origin=origin)


class InvalidURLError(ScrapeError):
    def __init__(
        self, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None, url: URL | str = ""
    ) -> None:
        """This error will be thrown when parsed URL is not valid."""
        ui_failure = "Invalid URL"
        self.url = url
        super().__init__(ui_failure, message=message, origin=origin)


class LoginError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when the login fails for a site."""
        ui_failure = "Failed Login"
        super().__init__(ui_failure, message=message, origin=origin)


class JDownloaderError(CDLBaseError):
    """This error will be thrown for any Jdownloader error."""


class InvalidYamlError(CDLBaseError):
    def __init__(self, file: Path, e: Exception) -> None:
        """This error will be thrown when a yaml config file has invalid values."""
        file_path = file.resolve()
        ui_failure = "Invalid YAML"
        msg = f"Unable to read file '{file_path}'"
        if isinstance(e, YAMLError):
            msg = f"File '{file_path}' is not a valid YAML file"
        mark = getattr(e, "problem_mark", None)
        if mark:
            msg += f"\n\nThe error was found in this line: \n {mark}"

        problem = getattr(e, "problem", str(e))
        msg += f"\n\n{problem.capitalize()}"
        msg += f"\n\n{VALIDATION_ERROR_FOOTER}"
        super().__init__(ui_failure, message=msg, origin=file)


@singledispatch
def create_error_msg(error: int) -> str:
    try:
        msg = HTTPStatus(error).phrase
        return f"{error} {msg}"
    except ValueError:
        cloudflare_error = CLOUDFLARE_ERRORS.get(error)
        if cloudflare_error:
            return f"{error} {cloudflare_error}"
    return f"{error} HTTP Error"


@create_error_msg.register
def _(error: str) -> str:
    return error


def get_origin(origin: ScrapeItem | Path | MediaItem | URL | None = None) -> Path | URL | None:
    if origin and not isinstance(origin, URL | Path):
        return origin.parents[0] if origin.parents else None
    return origin


class ErrorLogMessage:
    ui_failure: str
    main_log_msg: str
    csv_log_msg: str

    def __init__(self, ui_failure: str, main_log_msg: str = "", csv_log_msg: str = "") -> None:
        self.ui_failure = ui_failure
        self.main_log_msg = main_log_msg or ui_failure
        self.csv_log_msg = csv_log_msg or ui_failure
        if self.csv_log_msg == "Unknown":
            self.csv_log_msg = "See Logs for details"

    @classmethod
    def from_unknown_exc(cls, e: Exception) -> ErrorLogMessage:
        e_status = getattr(e, "status", None)
        e_message = getattr(e, "message", None)
        ui_failure = create_error_msg(e_status) if e_status else "Unknown"
        log_msg = e_message or str(e)
        return ErrorLogMessage(ui_failure, log_msg)
