from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


CDN_HOSTS = "litter.catbox.moe", "files.catbox.moe"


class CatboxCrawler(Crawler):
    SUPPORTED_HOSTS: ClassVar[tuple[str, ...]] = CDN_HOSTS
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {"Direct links": ""}
    primary_base_domain = AbsoluteHttpURL("https://catbox.moe")
    DOMAIN = "catbox.moe"
    FOLDER_DOMAIN = "Catbox"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p == scrape_item.url.host for p in CDN_HOSTS):
            return await self.direct_file(scrape_item, assume_ext=".zip")
        raise ValueError
