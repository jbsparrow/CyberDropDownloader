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

IMAGE_SELECTOR = "div[class=block-video] a img"
CONTENT_SELECTOR = "div[id=list_videos_common_videos_list_items] div a"


class NudoStarTVCrawler(Crawler):
    primary_base_domain = URL("https://nudostar.tv/")
    next_page_selector = "li[class=next] a"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "nudostar.tv", "NudoStarTV")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "models" not in scrape_item.url.parts:
            raise ValueError
        if scrape_item.url.name:
            scrape_item.url = scrape_item.url / ""
        if len(scrape_item.url.parts) > 4:
            return await self.image(scrape_item)
        await self.model(scrape_item)

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a model page."""
        title = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = self.create_title(soup.title.text.split("/")[0])  # type: ignore
                scrape_item.setup_as_album(title)

            if "Last OnlyFans Updates" in title or not soup.select_one(CONTENT_SELECTOR):
                raise ScrapeError(404)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, CONTENT_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        image = soup.select_one(IMAGE_SELECTOR)
        link_str: str = image.get("src")  # type: ignore
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
