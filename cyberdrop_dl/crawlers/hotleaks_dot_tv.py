from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers.leakedzone import LeakedZoneCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

PRIMARY_URL = AbsoluteHttpURL("https://hotleaks.tv")
IMAGES_CDN = AbsoluteHttpURL("https://image-cdn.hotleaks.tv")


class HotLeaksTVCrawler(LeakedZoneCrawler):
    DOMAIN: ClassVar[str] = "hotleaks.tv"
    FOLDER_DOMAIN: ClassVar[str] = "HotLeaksTV"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    IMAGES_CDN: ClassVar[AbsoluteHttpURL] = IMAGES_CDN
