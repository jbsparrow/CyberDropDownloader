from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


IMAGE_SELECTOR = "a[class=image]"


class XBunkrCrawler(Crawler):
    primary_base_domain = URL("https://xbunkr.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "xbunkr", "XBunkr")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        assert scrape_item.url.host
        if "media" in scrape_item.url.host:
            await self.file(scrape_item)
        return await self.album(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        album_id = scrape_item.url.parts[2]
        title = self.create_title(soup.select_one("h1[id=title]").text, scrape_item.album_id)  # type: ignore
        scrape_item.setup_as_album(title, album_id=album_id)

        for _, link in self.iter_tags(soup, IMAGE_SELECTOR):
            filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
            await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)
