from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://catbox.moe")
CDN_HOSTS = "litter.catbox.moe", "files.catbox.moe"


class CatboxCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = CDN_HOSTS
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Direct links": ""}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "catbox.moe"
    FOLDER_DOMAIN: ClassVar[str] = "Catbox"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p == scrape_item.url.host for p in CDN_HOSTS):
            return await self.direct_file(scrape_item, assume_ext=".zip")
        raise ValueError
