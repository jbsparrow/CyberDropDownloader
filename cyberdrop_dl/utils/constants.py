import re
from enum import IntEnum
from pathlib import Path

from rich.text import Text

# logging
CONSOLE_LEVEL = 100
MAX_NAME_LENGTHS = {"FILE": 95, "FOLDER": 60}
DEFAULT_CONSOLE_WIDTH = 240
DEBUG_VAR = False
CONSOLE_DEBUG_VAR = False
CSV_DELIMITER = ","
LOG_OUTPUT_TEXT = Text("")
RICH_HANDLER_CONFIG = {"show_time": True, "rich_tracebacks": True, "tracebacks_show_locals": False}
RICH_HANDLER_DEBUG_CONFIG = {
    "show_time": True,
    "rich_tracebacks": True,
    "tracebacks_show_locals": True,
    "locals_max_string": DEFAULT_CONSOLE_WIDTH,
    "tracebacks_extra_lines": 2,
    "locals_max_length": 20,
}


# regex
RAR_MULTIPART_PATTERN = re.compile(r"^part\d+")
SANITIZE_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\']')
REGEX_LINKS = re.compile(r"(?:http.*?)(?=($|\n|\r\n|\r|\s|\"|\[/URL]|']\[|]\[|\[/img]))")


class CustomHTTPStatus(IntEnum):
    WEB_SERVER_IS_DOWN = 521
    IM_A_TEAPOT = 418
    DDOS_GUARD = 429


BLOCKED_DOMAINS = ("facebook", "instagram", "fbcdn")

STYLE_TO_DIFF_FORMAT_MAP = {
    "default": "{}",
    "green": "+   {}",
    "red": "-   {}",
    "yellow": "*** {}",
}

APP_STORAGE = Path("./AppData")
DOWNLOAD_STORAGE = Path("./Downloads")


# Pypi
PRELEASE_TAGS = {
    "dev": "Development",
    "pre": "Pre-Release",
    "post": "Post-Release",
    "rc": "Release Candidate",
    "a": "Alpha",
    "b": "Beta",
}

PRELEASE_VERSION_PATTERN = r"(\d+)\.(\d+)\.(\d+)(?:\.([a-z]+)\d+|([a-z]+)\d+)"
PYPI_JSON_URL = "https://pypi.org/pypi/cyberdrop-dl-patched/json"

# file formats
FILE_FORMATS = {
    "Images": {
        ".gif",
        ".gifv",
        ".jfif",
        ".jif",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".png",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
    },
    "Videos": {
        ".avchd",
        ".avi",
        ".f4v",
        ".flv",
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
        ".qt",
        ".swf",
        ".ts",
        ".webm",
        ".wmv",
    },
    "Audio": {
        ".flac",
        ".m4a",
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
    "7z": {".7z", ".tar", ".gz", ".bz2", ".zip"},
}
