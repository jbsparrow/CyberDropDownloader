from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.types import AbsoluteHttpURL

from ._yetishare import YetiShareCrawler


class CyberfileCrawler(YetiShareCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://cyberfile.me/")
    DOMAIN: ClassVar[str] = "cyberfile"
