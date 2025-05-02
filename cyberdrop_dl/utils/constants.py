import re
import string
import sys
from datetime import UTC, datetime
from enum import Enum, IntEnum, StrEnum, auto
from pathlib import Path
from typing import Any

from rich.text import Text

# TIME
STARTUP_TIME = datetime.now()
STARTUP_TIME_UTC = datetime.now(UTC)
LOGS_DATETIME_FORMAT = "%Y%m%d_%H%M%S"
LOGS_DATE_FORMAT = "%Y_%m_%d"
STARTUP_TIME_STR = STARTUP_TIME.strftime(LOGS_DATETIME_FORMAT)
STARTUP_TIME_UTC_STR = STARTUP_TIME_UTC.strftime(LOGS_DATETIME_FORMAT)


# logging
CONSOLE_LEVEL = 100
MAX_NAME_LENGTHS = {"FILE": 95, "FOLDER": 60}
DEFAULT_CONSOLE_WIDTH = 240
CSV_DELIMITER = ","
LOG_OUTPUT_TEXT = Text("")
RICH_HANDLER_CONFIG: dict[str, Any] = {"rich_tracebacks": True, "tracebacks_show_locals": False}
RICH_HANDLER_DEBUG_CONFIG = RICH_HANDLER_CONFIG | {
    "tracebacks_show_locals": True,
    "locals_max_string": DEFAULT_CONSOLE_WIDTH,
    "tracebacks_extra_lines": 2,
    "locals_max_length": 20,
}
VALIDATION_ERROR_FOOTER = """Please delete the file or fix the errors. Read the documentation to learn what's the expected format and values: https://script-ware.gitbook.io/cyberdrop-dl/reference/configuration-options
\nThis is not a bug. Do not open issues related to this"""


CLI_VALIDATION_ERROR_FOOTER = """Please read the documentation to learn about the expected values: https://script-ware.gitbook.io/cyberdrop-dl/reference/configuration-options
\nThis is not a bug. Do not open issues related to this"""


NOT_PRINTABLE_ASCII_CHARS = "".join(char for c in range(128) if (char := chr(c)) not in string.printable)
INVALID_UNIX_FILENAME_CHARS = NOT_PRINTABLE_ASCII_CHARS + "/"
INVALID_WIN_FILENAME_CHARS = INVALID_UNIX_FILENAME_CHARS + ':*?"<>|\t\n\r\x0b\x0c\\'
RESERVED_WIN_NAMES = ["CON", "PRN", "AUX", "NUL", "COM1"]
RESERVED_WIN_NAMES.extend([f"COM{i}" for i in range(10)])
RESERVED_WIN_NAMES.extend([f"LPT{i}" for i in range(10)])

IS_WINDOWS = IS_MACOS = IS_LINUX = False
if sys.platform == "win32":
    IS_WINDOWS = True
    MAX_PATH_LEN = 255

elif sys.platform == "darwin":
    IS_MACOS = True
    MAX_PATH_LEN = 1024
else:
    IS_LINUX = True
    MAX_PATH_LEN = 4096

# regex
if IS_WINDOWS:
    SANITIZE_FILENAME_PATTERN = re.compile(INVALID_WIN_FILENAME_CHARS)
else:
    SANITIZE_FILENAME_PATTERN = re.compile(INVALID_UNIX_FILENAME_CHARS)
RAR_MULTIPART_PATTERN = re.compile(r"^part\d+")
REGEX_LINKS = re.compile(r"(?:http.*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]))")


class CustomHTTPStatus(IntEnum):
    WEB_SERVER_IS_DOWN = 521
    IM_A_TEAPOT = 418
    DDOS_GUARD = 429


BLOCKED_DOMAINS = ("facebook", "instagram", "fbcdn")


APP_STORAGE = Path("./AppData")
DOWNLOAD_STORAGE = Path("./Downloads")
RESERVED_CONFIG_NAMES = ["all", "default"]


class BROWSERS(StrEnum):
    chrome = auto()
    firefox = auto()
    safari = auto()
    edge = auto()
    opera = auto()
    brave = auto()
    librewolf = auto()
    opera_gx = auto()
    vivaldi = auto()
    chromium = auto()


class NotificationResult(Enum):
    SUCCESS = Text("Success", "green")
    FAILED = Text("Failed", "bold red")
    PARTIAL = Text("Partial Success", "yellow")
    NONE = Text("No Notifications Sent", "yellow")


# file formats
FILE_FORMATS = {
    "Images": {
        ".gif",
        ".gifv",
        ".heic",
        ".jfif",
        ".jif",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".jxl",
        ".png",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
    },
    "Videos": {
        ".3gp",
        ".avchd",
        ".avi",
        ".f4v",
        ".flv",
        ".m2ts",
        ".m4p",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp2",
        ".mp4",
        ".mpe",
        ".mpeg",
        ".mpg",
        ".mpv",
        ".mts",
        ".ogg",
        ".ogv",
        ".qt",
        ".swf",
        ".ts",
        ".webm",
        ".wmv",
    },
    "Audio": {
        ".flac",
        ".m4a",
        ".mka",
        ".mp3",
        ".wav",
    },
    "Text": {
        ".htm",
        ".html",
        ".md",
        ".nfo",
        ".txt",
    },
    "7z": {
        ".7z",
        ".bz2",
        ".gz",
        ".tar",
        ".zip",
    },
}


MEDIA_EXTENSIONS = FILE_FORMATS["Audio"] | FILE_FORMATS["Videos"] | FILE_FORMATS["Images"]
DISABLE_CACHE = None
