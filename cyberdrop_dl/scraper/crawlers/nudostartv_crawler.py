from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem


class NudoStarTVCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "nudostartv", "NudoStarTV")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        scrape_item.url = URL(str(scrape_item.url) + "/")
        await self.profile(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(soup.select_one("title").get_text().split("/")[0], None, None)
        content = soup.select("div[id=list_videos_common_videos_list_items] div a")
        for page in content:
            link = URL(page.get("href"))
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            await self.image(new_scrape_item)
        next_page = soup.select_one("li[class=next] a")
        if next_page:
            link = URL(next_page.get("href"))
            new_scrape_item = self.create_scrape_item(scrape_item, link, "")
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        content = soup.select("div[class=block-video] a img")
        for image in content:
            link = URL(image.get("src"))
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
