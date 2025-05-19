from __future__ import annotations

import calendar
from datetime import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

ALBUM_TITLE_SELECTOR = "span[class=author-header__album-name]"
DATE_SELECTOR = "span[class=date-time]"
FILES_SELECTOR = 'a[class*="image-wrapper center-cropped im-wr"]'
IMAGE_SELECTOR = ".main-image-wrapper"


class PimpAndHostCrawler(Crawler):
    primary_base_domain = URL("https://pimpandhost.com/")
    next_page_selector = "li[class=next] a"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pimpandhost", "PimpAndHost")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                album_id = scrape_item.url.parts[2]
                title_portion = soup.select_one(ALBUM_TITLE_SELECTOR).get_text()  # type: ignore
                title = self.create_title(title_portion, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)

                if date_tag := soup.select_one(DATE_SELECTOR):
                    scrape_item.possible_datetime = self.parse_datetime(date_tag.get("title"))  # type: ignore

            for _, new_scrape_item in self.iter_children(scrape_item, soup, FILES_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        link_tag = soup.select_one(IMAGE_SELECTOR)
        link_str: str = link_tag.get("data-src")  # type: ignore
        link = self.parse_url(link_str)
        date_str: str = soup.select_one(DATE_SELECTOR).get("title")  # type: ignore
        scrape_item.possible_datetime = self.parse_datetime(date_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.strptime(date, "%A, %B %d, %Y %I:%M:%S%p %Z")
        return calendar.timegm(parsed_date.timetuple())
