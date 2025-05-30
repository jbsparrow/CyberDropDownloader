from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

DOWNLOAD_SELECTOR = "a[class*='download-button']"
HOMEPAGE_CATCHALL_FILE = "/s21/FHVZKQyAZlIsrneDAsp.jpeg"


class FileditchCrawler(Crawler):
    primary_base_domain = URL("https://fileditchfiles.me/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "fileditch", "Fileditch")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.path != "/file.php":
            # Some old files are only direct linkable
            return await self.direct_file(scrape_item)
        return await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        link_str: str = soup.select_one(DOWNLOAD_SELECTOR).get("href")  # type: ignore
        link = self.parse_url(link_str)
        if link.path == HOMEPAGE_CATCHALL_FILE:
            raise ScrapeError(422)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
