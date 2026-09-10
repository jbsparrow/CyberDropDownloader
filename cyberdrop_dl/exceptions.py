from __future__ import annotations

import dataclasses
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, final

if TYPE_CHECKING:
    import datetime
    from collections.abc import Sequence

    import yarl
    from yaml import YAMLError


class HasParents(Protocol):
    @property
    def parents(self) -> Sequence[yarl.URL]: ...


class MediaItemLike(HasParents, Protocol):
    @property
    def uploaded_at_date(self) -> datetime.datetime | None: ...
    @property
    def ext(self) -> str: ...
    @property
    def duration(self) -> float | None: ...


def _format_error(ui_failure: str, message: str, notes: Sequence[str] | None = None) -> str:
    msg = message if ui_failure == message else f"{ui_failure} - {message}"
    if notes:
        msg = msg + "\n" + "\n".join(f"[NOTE]: {note}" for note in notes)
    return msg


# See: https://developers.cloudflare.com/support/troubleshooting/cloudflare-errors/troubleshooting-cloudflare-5xx-errors/
CLOUDFLARE_HTTP_ERROR_CODES = {
    520: "Unexpected Response",
    521: "Web Server Down",
    522: "Connection Timeout",
    523: "Origin Is Unreachable",
    524: "Response Timeout",
    525: "SSL Handshake Failed",
    526: "Untrusted",
    530: "IP Banned / Restricted",
}

# https://en.wikipedia.org/wiki/List_of_HTTP_status_codes#Nonstandard_codes
# Not all of them, just the ones we actually expect to see and do not shadow standard ones
NON_STANDARD_HTTP_ERROR_CODES = {
    419: "Page Expired",
    509: "Bandwidth Limit Exceeded",
    999: "Timeout",
}

HTTP_ERROR_CODES = {
    **NON_STANDARD_HTTP_ERROR_CODES,
    **CLOUDFLARE_HTTP_ERROR_CODES,
    **{code.value: code.phrase for code in HTTPStatus},
}


def _notes(e: BaseException) -> list[str] | tuple[()]:
    return getattr(e, "__notes__", ())


class DatabaseError(RuntimeError): ...


class CDLBaseError(Exception):
    """Base exception for cyberdrop-dl errors."""

    def __init__(
        self,
        ui_failure: str = "Something went wrong",
        *,
        message: str | None = None,
        status: str | int | None = None,
        origin: HasParents | yarl.URL | Path | None = None,
    ) -> None:
        self.ui_failure: str = ui_failure
        self.message: str = message or ui_failure
        self.origin: Path | yarl.URL | None = get_origin(origin)
        super().__init__(self.message)
        if status:
            self.status: str | int | None = status
            super().__init__(self.status)

    def __str__(self) -> str:
        return _format_error(self.ui_failure, self.message, _notes(self))


class FlaresolverrError(CDLBaseError):
    def __init__(self, message: str | None = None) -> None:
        ui_failure = "Flaresolverr Error"
        super().__init__(ui_failure, message=message)


class InvalidContentTypeError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when the content type isn't as expected."""
        ui_failure = "Invalid Content Type"
        super().__init__(ui_failure, message=message, origin=origin)


class FileNameError(CDLBaseError): ...


class NoExtensionError(FileNameError):
    def __init__(self, filename: str | None = None, *, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when no extension is given for a file."""
        ui_failure = "No File Extension"
        super().__init__(ui_failure, message=filename, origin=origin)

    def __str__(self) -> str:
        return f"{self.ui_failure} ({self.message})"


class InvalidExtensionError(NoExtensionError):
    def __init__(self, filename: str | None = None, *, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when no extension is given for a file."""
        super().__init__(filename=filename, origin=origin)
        self.ui_failure = "Invalid File Extension"


class PathTraversalError(CDLBaseError):
    def __init__(self, path: Path) -> None:
        ui_failure = "Path Traversal"
        msg = f"Download path '{path}' is outside destination download path"
        super().__init__(ui_failure, message=msg)


class PasswordProtectedError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when a file is password protected."""
        ui_failure = "Password Protected"
        msg = message or "File/Folder is password protected"
        super().__init__(ui_failure, message=msg, origin=origin)


class MaxChildrenError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when an scrape item reaches its max number or children."""
        ui_failure = "Max Children Reached"
        msg = message or "Max number of children reached"
        super().__init__(ui_failure, message=msg, origin=origin)


class DDOSGuardError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when DDoS-Guard is detected."""
        ui_failure = "DDoS-Guard"
        msg = message or "DDoS-Guard detected"
        super().__init__(ui_failure, message=msg, origin=origin)


class DownloadError(CDLBaseError):
    def __init__(
        self,
        status: str | int,
        message: str | None = None,
        origin: HasParents | yarl.URL | None = None,
        *,
        retry: bool = False,
    ) -> None:
        """This error will be thrown when a download fails."""
        ui_failure = create_error_msg(status)
        msg = message
        self.retry: bool = retry
        super().__init__(ui_failure, message=msg, status=status, origin=origin)


class SlowDownloadError(DownloadError):
    def __init__(self, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when a file will be skipped do to a low download speed."""
        ui_failure = "Slow Download"
        super().__init__(ui_failure, origin=origin)


class InsufficientFreeSpaceError(CDLBaseError):
    def __init__(self, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when no enough storage is available."""
        ui_failure = "Insufficient Free Space"
        super().__init__(ui_failure, origin=origin)


class SkipDownloadError(CDLBaseError):
    """Throw this when a download is not allowed by config options"""


class RestrictedFiletypeError(SkipDownloadError):
    def __init__(self, origin: MediaItemLike) -> None:
        """This error will be thrown when has a filetype not allowed by config."""
        ui_failure = "Restricted File Ext"
        message = f"File extension ({origin.ext}) ignored by config options"
        super().__init__(ui_failure, message=message, origin=origin)


class DurationError(SkipDownloadError):
    def __init__(self, origin: MediaItemLike) -> None:
        """This error will be thrown when the file duration is not allowed by the config."""
        ui_failure = "Duration Not Allowed"
        message = f"File duration ({origin.duration}s) out of config range"
        super().__init__(ui_failure, message=message, origin=origin)


class RestrictedDateRangeError(SkipDownloadError):
    def __init__(self, origin: MediaItemLike) -> None:
        """This error will be thrown when the publication date of the media item is not allowed by config."""
        ui_failure = "Restricted DateRange"
        message = f"File upload date ({origin.uploaded_at_date}s) out of config range"
        super().__init__(ui_failure, message=message, origin=origin)


class ScrapeError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: HasParents | yarl.URL | None = None
    ) -> None:
        """This error will be thrown when a scrape fails."""
        ui_failure = create_error_msg(status)
        super().__init__(ui_failure, message=message, status=status, origin=origin)

    @staticmethod
    def unsupported() -> ScrapeError:
        return ScrapeError("Unknown URL path")


class LoginError(CDLBaseError):
    def __init__(self, message: str | None = None, *, origin: HasParents | yarl.URL | None = None) -> None:
        """This error will be thrown when the login fails for a site."""
        ui_failure = "Failed Login"
        super().__init__(ui_failure, message=message, origin=origin)


class JDownloaderError(CDLBaseError):
    """This error will be thrown for any Jdownloader error."""

    def __init__(self, message: str | None = None) -> None:
        ui_failure = "JDownloader Error"
        super().__init__(ui_failure, message=message)


class InvalidYamlError(CDLBaseError):
    def __init__(self, file: Path, e: YAMLError) -> None:
        """This error will be thrown when a yaml config file has invalid values."""
        file = file.resolve()
        ui_failure = "Invalid YAML"
        msg = f"'{file}' is not a valid YAML file"

        if mark := getattr(e, "problem_mark", None):
            msg += f"\n\nThe error was found in this line: \n {mark}"

        problem = getattr(e, "problem", str(e)).capitalize()
        msg += f"\n\n{problem}\n\nPlease delete the file or fix the errors"
        super().__init__(ui_failure, message=msg, origin=file)


def create_error_msg(error: int | str) -> str:
    if isinstance(error, str):
        return error
    if phrase := HTTP_ERROR_CODES.get(error):
        return f"{error} {phrase}"

    if 300 <= error < 400:
        return f"HTTP Redirection ({error})"
    if 400 <= error < 500:
        return f"HTTP Client Error ({error})"
    if 500 <= error < 600:
        return f"HTTP Server Error ({error})"

    return f"Unknown ({error})"


def get_origin(origin: HasParents | Path | yarl.URL | None = None) -> Path | yarl.URL | None:
    import yarl

    if origin is None:
        return None
    if type(origin) is yarl.URL:
        return origin
    if isinstance(origin, Path):
        return origin
    return origin.parents[0] if origin.parents else None  # pyright: ignore[reportAttributeAccessIssue]


@final
@dataclasses.dataclass(slots=True)
class CDLAppError(RuntimeError):
    ui_error: str
    msg: str = ""
    csv_msg: str = ""

    def __post_init__(self) -> None:
        self.msg = self.msg or self.ui_error
        self.csv_msg = self.csv_msg or self.ui_error
        if self.csv_msg == "Unknown":
            self.csv_msg = "See logs for details"

    @staticmethod
    def from_unknown_exc(e: Exception) -> CDLAppError:
        assert type(e) is not CDLAppError
        e_status = getattr(e, "status", None)
        e_message = getattr(e, "message", None)
        ui_failure = create_error_msg(e_status) if e_status else "Unknown"
        log_msg = _format_error(ui_failure, e_message or f"{type(e).__name__}({e!s})", _notes(e))
        return CDLAppError(ui_failure, log_msg)


class CDLConfigRuntimeErrorsGroup(ExceptionGroup): ...
