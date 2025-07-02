from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


CDN_HOST = "pbs.twimg.com"
PRIMARY_URL = AbsoluteHttpURL("https://twimg.com/")


class TwimgCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Photo": "/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "twimg"
    FOLDER_DOMAIN: ClassVar[str] = "TwitterImages"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "video" in scrape_item.url.host:
            return await self.direct_file(scrape_item)
        await self.photo(scrape_item)

    async def photo(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None) -> None:
        # https://developer.x.com/en/docs/x-api/v1/data-dictionary/object-model/entities#photo_format
        link = url or scrape_item.url
        if "emoji" in link.parts:
            return
        # name could be "orig", "large", "medium", "small"
        # `orig`` is original quality but it's not always available
        link = link.with_host(CDN_HOST).with_query(format="jpg", name="large")
        filename = Path(link.name).with_suffix(".jpg").as_posix()
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)
