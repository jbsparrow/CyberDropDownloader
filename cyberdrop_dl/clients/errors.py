from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from yarl import URL

if TYPE_CHECKING:
    from yaml.constructor import ConstructorError

    from cyberdrop_dl.scraper.crawler import ScrapeItem
    from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem


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
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when a file is password protected."""
        ui_message = "Password Protected"
        message = message or "File/Folder is password protected"
        super().__init__(ui_message, message=message, origin=origin)


class MaxChildrenError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when an scrape item reaches its max number or children."""
        ui_message = "Max Children Reached"
        message = message or "Max number of children reached"
        super().__init__(ui_message, message=message, origin=origin)


class DDOSGuardError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when DDoS-Guard is detected."""
        ui_message = "DDoS-Guard"
        message = message or "DDoS-Guard detected"
        super().__init__(ui_message, message=message, origin=origin)


class DownloadError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None
    ) -> None:
        """This error will be thrown when a download fails."""
        ui_message = str(status)
        if isinstance(status, int):
            try:
                ui_message = f"{status} {HTTPStatus(status).phrase}"
            except ValueError:
                ui_message = f"{status} HTTP Error"
        super().__init__(ui_message, message=message, status=status, origin=origin)


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


class ScrapeError(CDLBaseError):
    def __init__(
        self, status: str | int, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None
    ) -> None:
        """This error will be thrown when a scrape fails."""
        ui_message = str(status)
        if isinstance(status, int):
            try:
                ui_message = f"{status} {HTTPStatus(status).phrase}"
            except ValueError:
                ui_message = f"{status} HTTP Error"
        super().__init__(ui_message, message=message, status=status, origin=origin)


class LoginError(CDLBaseError):
    def __init__(self, *, message: str | None = None, origin: ScrapeItem | MediaItem | URL | None = None) -> None:
        """This error will be thrown when the login fails for a site."""
        ui_message = "Failed Login"
        super().__init__(ui_message, message=message, origin=origin)


class JDownloaderError(CDLBaseError):
    """This error will be thrown for any Jdownloader error."""


class InvalidYamlError(CDLBaseError):
    def __init__(self, file: Path, e: ConstructorError) -> None:
        """This error will be thrown when a yaml config file has invalid values."""
        mark = e.problem_mark if hasattr(e, "problem_mark") else e
        message = f"ERROR: File '{file}' has an invalid config. Please verify and edit it manually\n {mark}"
        self.message_rich = message.replace("ERROR:", "[bold red]ERROR:[/bold red]")
        super().__init__("Invalid YAML", message=message, origin=file)
