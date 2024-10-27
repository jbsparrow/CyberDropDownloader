from typing import TYPE_CHECKING, Optional
from http import HTTPStatus

if TYPE_CHECKING:
    from cyberdrop_dl.scraper.crawler import ScrapeItem
    from yaml.constructor import ConstructorError
    from yarl import URL
    from pathlib import Path

class CDLBaseException(Exception):
    """Base exception for cyberdrop-dl errors"""
   
    def __init__(self, ui_message: str = "Something went wrong", *, message: Optional[str] = None , status: Optional[int]=None, origin: Optional[ScrapeItem | URL | Path] = None):
        self.ui_message = ui_message
        self.message = message if message else ui_message
        self.origin = origin 
        if isinstance(origin, ScrapeItem): 
            self.origin = origin.parents[0] if origin.parents else None
        super().__init__(self.message)
        if status:
            self.status = status
            super().__init__(self.status)

class InvalidContentTypeFailure(CDLBaseException):
    def __init__(self, *, message: str = "Invalid Content Type", origin: Optional[ScrapeItem | URL] = None):
        """This error will be thrown when the content type isn't as expected"""
        ui_message = "Invalid Content Type"
        super().__init__(ui_message, message = message, origin=origin)

class NoExtensionFailure(CDLBaseException):
    def __init__(self, *, message: str = "No File Extension", origin: Optional[ScrapeItem | URL] = None):
        """This error will be thrown when no extension is given for a file"""
        ui_message = "No File Extension"
        super().__init__(ui_message, message = message, origin=origin)


class PasswordProtected(CDLBaseException):
    def __init__(self, *, message: str = "File/Folder is password protected", origin: Optional[ScrapeItem | URL] = None ):
        """This error will be thrown when a file is password protected"""
        ui_message = "Password Protected"
        super().__init__(ui_message, message = message, origin=origin)


class DDOSGuardFailure(CDLBaseException):
    def __init__(self, *, message: str = "DDoS-Guard detected", origin: Optional[ScrapeItem | URL] = None):
        """This error will be thrown when DDoS-Guard is detected"""
        ui_message = "DDoS-Guard"
        super().__init__(ui_message, message = message, origin=origin)


class DownloadFailure(CDLBaseException):
    def __init__(self, status: int, message: Optional[str] = "Download Failure" , origin: Optional[ScrapeItem | URL] = None):
        """This error will be thrown when a request fails"""
        ui_message = f"{status} {HTTPStatus(status).phrase}"
        super().__init__(ui_message, message = message, status = status, origin=origin)

class ScrapeFailure(CDLBaseException):
    def __init__(self, status: int, message: Optional[str] = "Scrape Failure" , origin: Optional[ScrapeItem | URL] = None):
        """This error will be thrown when a scrape fails"""
        ui_message = f"{status} {HTTPStatus(status).phrase}"
        super().__init__(ui_message, message = message, status = status, origin=origin)

class FailedLoginFailure(CDLBaseException):
    def __init__(self, *, message: str = "Failed Login", origin: Optional[ScrapeItem | URL] = None):
        """This error will be thrown when the login fails for a site"""
        ui_message = "Failed Login"
        super().__init__(ui_message, message = message, origin=origin)


class JDownloaderFailure(CDLBaseException):
    """This error will be thrown for any Jdownloader error"""
    pass

class InvalidYamlConfig(CDLBaseException):
    def __init__(self, file: Path, e: ConstructorError):
        """This error will be thrown when a yaml config file has invalid values"""
        mark = e.problem_mark if hasattr(e, 'problem_mark') else e
        message = f"ERROR: File '{file}' has an invalid config. Please verify and edit it manually\n {mark}"
        self.message_rich = message.replace("ERROR:", "[bold red]ERROR:[/bold red]")
        super().__init__('Invalid YAML', message = message, origin = file)
