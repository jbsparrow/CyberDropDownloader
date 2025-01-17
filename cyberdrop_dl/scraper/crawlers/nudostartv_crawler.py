from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class NudoStarTVCrawler(Crawler):
    primary_base_domain = URL("https://nudostar.tv/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "nudostartv", "NudoStarTV")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        scrape_item.url = URL(str(scrape_item.url) + "/")
        await self.model(scrape_item)

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True
        title = self.create_title(soup.select_one("title").get_text().split("/")[0])
        content = soup.select("div[id=list_videos_common_videos_list_items] div a")
        for page in content:
            link_str: str = page.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            await self.image(new_scrape_item)
            scrape_item.add_children()

        next_page = soup.select_one("li[class=next] a")
        if next_page:
            link_str: str = next_page.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        image = soup.select_one("div[class=block-video] a img")
        link_str: str = image.get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
