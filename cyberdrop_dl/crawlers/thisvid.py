from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers._kvs import KernelVideoSharingCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


class ThisVidCrawler(KernelVideoSharingCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://thisvid.com")
    DOMAIN: ClassVar[str] = "thisvid"
    FOLDER_DOMAIN: ClassVar[str] = "ThisVid"
