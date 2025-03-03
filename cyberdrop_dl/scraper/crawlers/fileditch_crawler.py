from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class FileditchCrawler(Crawler):
    primary_base_domain = URL("https://fileditchfiles.me/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "fileditch", "Fileditch")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.path == "/file.php":
            await self.file(scrape_item)
        else:
            await self.file_legacy(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        link_str: str = soup.select_one("a[class*='download-button']").get("href")
        link = self.parse_url(link_str)
        if link.path == "/s21/FHVZKQyAZlIsrneDAsp.jpeg":  # homepage
            raise ScrapeError(999, "assertion failed")
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def file_legacy(self, scrape_item: ScrapeItem) -> None:
        # Some old files are only direct linkable
        filename, ext = get_filename_and_ext(scrape_item.url.path)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)
