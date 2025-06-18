from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class NudoStarCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://nudostar.com/forum/")
    DOMAIN: ClassVar[str] = "nudostar"
    FOLDER_DOMAIN: ClassVar[str] = "NudoStar"
