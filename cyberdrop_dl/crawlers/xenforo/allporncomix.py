from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class AllPornComixCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://forum.allporncomix.com")
    DOMAIN: ClassVar[str] = "allporncomix"
    FOLDER_DOMAIN: ClassVar[str] = "AllPornComix"
    login_required = False
    IGNORE_EMBEDED_IMAGES_SRC: ClassVar = False
