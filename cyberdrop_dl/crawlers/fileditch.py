from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

DOWNLOAD_SELECTOR = "a[class*='download-button']"
HOMEPAGE_CATCHALL_FILE = "/s21/FHVZKQyAZlIsrneDAsp.jpeg"

PRIMARY_URL = AbsoluteHttpURL("https://fileditchfiles.me/")


class FileditchCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Direct links": ""}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "fileditch"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.path != "/file.php":
            # Some old files are only direct linkable
            return await self.direct_file(scrape_item)
        return await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        link_str: str = css.select_one_get_attr(soup, DOWNLOAD_SELECTOR, "href")
        link = self.parse_url(link_str)
        if link.path == HOMEPAGE_CATCHALL_FILE:
            raise ScrapeError(422)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
