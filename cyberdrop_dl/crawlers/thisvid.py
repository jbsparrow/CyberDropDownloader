from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers._kvs import KernelVideoSharingCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

PRIMARY_URL = AbsoluteHttpURL("https://thisvid.com")


class ThisVidCrawler(KernelVideoSharingCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "thisvid"
    FOLDER_DOMAIN: ClassVar[str] = "ThisVid"
