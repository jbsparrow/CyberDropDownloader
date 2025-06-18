from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://buzzheavier.com")


class BuzzHeavierCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Direct links": ""}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "buzzheavier.com"
    FOLDER_DOMAIN: ClassVar[str] = "BuzzHeavier"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        return await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        url = scrape_item.url / "download"
        headers = {"HX-Current-URL": str(scrape_item.url), "HX-Request": "true"}
        async with self.request_limiter:
            response = await self.client._get_head(self.DOMAIN, url, headers=headers)

        assert response.content_disposition
        assert response.content_disposition.filename
        link = self.parse_url(response.headers["hx-redirect"])
        filename, ext = self.get_filename_and_ext(response.content_disposition.filename, assume_ext=".zip")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=link)
