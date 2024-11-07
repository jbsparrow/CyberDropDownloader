import re
from enum import IntEnum

from rich.text import Text

MAX_NAME_LENGTHS = {"FILE": 95, "FOLDER": 60}

DEFAULT_CONSOLE_WIDTH = 240
DEBUG_VAR = False
CONSOLE_DEBUG_VAR = False

LOG_OUTPUT_TEXT = Text("")

# regex
RAR_MULTIPART_PATTERN = re.compile(r"^part\d+")
SANITIZE_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\']')


class CustomHTTPStatus(IntEnum):
    WEB_SERVER_IS_DOWN = 521
    IM_A_TEAPOT = 418
    DDOS_GUARD = 429


STYLE_TO_DIFF_FORMAT_MAP = {
    "default": "{}",
    "green": "+   {}",
    "red": "-   {}",
    "yellow": "*** {}",
}


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
