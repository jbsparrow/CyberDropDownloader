from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class XBunkerCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://xbunker.nu/")
    DOMAIN: ClassVar[str] = "xbunker"
    FOLDER_DOMAIN: ClassVar[str] = "XBunker"
