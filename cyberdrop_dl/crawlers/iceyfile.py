from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from ._yetishare import YetiShareCrawler


class IceyFileCrawler(YetiShareCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://iceyfile.com/")
    DOMAIN: ClassVar[str] = "iceyfile"
