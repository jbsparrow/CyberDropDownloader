from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


CDN_HOST = "pbs.twimg.com"
PRIMARY_BASE_DOMAIN = AbsoluteHttpURL("https://twimg.com/")


class TwimgCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {"Photo": "/..."}
    primary_base_domain = PRIMARY_BASE_DOMAIN
    DOMAIN = "twimg"
    FOLDER_DOMAIN = "TwitterImages"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        await self.photo(scrape_item)

    async def photo(self, scrape_item: ScrapeItem) -> None:
        # https://developer.x.com/en/docs/x-api/v1/data-dictionary/object-model/entities#photo_format
        scrape_item.url = scrape_item.url.with_host(CDN_HOST)
        link = scrape_item.url.with_query(format="jpg", name="large")
        filename = Path(link.name).with_suffix(".jpg").as_posix()
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)
