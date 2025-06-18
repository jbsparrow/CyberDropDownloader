from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .xenforo import XenforoCrawler


class LeakedModelsCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://leakedmodels.com/forum/")
    DOMAIN: ClassVar[str] = "leakedmodels"
    FOLDER_DOMAIN: ClassVar[str] = "LeakedModels"
