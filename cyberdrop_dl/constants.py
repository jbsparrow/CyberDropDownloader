from __future__ import annotations

import datetime
from contextvars import ContextVar
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any, Literal, final

from cyclopts import Parameter
from typing_extensions import Sentinel

from cyberdrop_dl import __version__

if TYPE_CHECKING:
    from pathlib import Path

type ImpersonateTarget = Literal["chrome", "edge", "safari", "safari_ios", "chrome_android", "firefox"]

LOGS_DATETIME_FORMAT = "%Y%m%d_%H%M%S"
LOGS_DATE_FORMAT = "%Y_%m_%d"
STARTUP_TIME_STR = datetime.datetime.now().strftime(LOGS_DATETIME_FORMAT)  # noqa: DTZ005
CDL_USER_AGENT = f"cyberdrop-dl/{__version__}"


MISSING: Any = Sentinel("MISSING")
HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"]

MAIN_LOG_FILE: ContextVar[Path] = ContextVar("MAIN_LOG_FILE")

DEFAULT_PARAMETER = Parameter(
    negative_iterable=[],
    json_dict=False,
    json_list=False,
    consume_multiple=True,
    allow_repeating=False,
)


class CIStrEnum(StrEnum):
    @classmethod
    def _missing_(cls, value: object) -> CIStrEnum | None:
        value = str(value).casefold()
        for member in cls:
            if member.name.casefold() == value:
                return member


class TempExt(StrEnum):
    HLS = ".cdl_hls"
    WRONG_CDL_HLS = ".cdl_hsl"  # used for a while in old versions, has a typo
    PART = ".part"


BLOCKED_DOMAINS = frozenset(
    (
        "facebook",
        "instagram",
        "fbcdn",
        "gfycat",
        "ko-fi.com",
        "paypal.me",
        "amazon.com",
        "throne.com",
        "youtu.be",
        "youtube.com",
        "linktr.ee",
        "beacons.page",
        "beacons.ai",
        "allmylinks.com",
    )
)


class HashMode(CIStrEnum):
    OFF = auto()
    IN_PLACE = auto()
    POST_DOWNLOAD = auto()

    @property
    def enabled(self) -> bool:
        return self is not HashMode.OFF


@final
class FileExt:
    IMAGE = frozenset(
        {
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
        }
    )
    VIDEO = frozenset(
        {
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
        }
    )
    AUDIO = frozenset(
        {
            ".flac",
            ".m4a",
            ".mka",
            ".mp3",
            ".wav",
        }
    )
    TEXT = frozenset(
        {
            ".htm",
            ".html",
            ".md",
            ".nfo",
            ".txt",
            ".vtt",
            ".sub",
        }
    )
    SEVEN_Z = frozenset(
        {
            ".7z",
            ".bz2",
            ".gz",
            ".tar",
            ".zip",
        }
    )
    VIDEO_OR_IMAGE = VIDEO | IMAGE
    MEDIA = AUDIO | VIDEO_OR_IMAGE
    DANGEROUS = frozenset(
        {
            ".bat",
            ".com",
            ".exe",
            ".hta",
            ".inf",
            ".jar",
            ".js",
            ".lnk",
            ".msc",
            ".msi",
            ".ps1",
            ".ps2",
            ".psc1",
            ".psc2",
            ".sh",
            ".scf",
            ".vb",
            ".vbs",
            ".wsc",
            ".wsh",
        }
    )
