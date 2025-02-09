from __future__ import annotations

import calendar
from datetime import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class PimpAndHostCrawler(Crawler):
    primary_base_domain = URL("https://pimpandhost.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pimpandhost", "PimpAndHost")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "album" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        title = self.create_title(
            soup.select_one("span[class=author-header__album-name]").get_text(), scrape_item.album_id
        )
        date_str: str = soup.select_one("span[class=date-time]").get("title")
        date = self.parse_datetime(date_str)

        files = soup.select('a[class*="image-wrapper center-cropped im-wr"]')
        for file in files:
            link_str: str = file.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                title,
                possible_datetime=date,
                add_parent=scrape_item.url,
            )
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

        next_page = soup.select_one("li[class=next] a")
        if next_page:
            next_page_str: str = next_page.get("href")
            next_page = self.parse_url(next_page_str)
            new_scrape_item = self.create_scrape_item(scrape_item, next_page, possible_datetime=date)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_tag = soup.select_one(".main-image-wrapper")
        link_str: str = link_tag.get("data-src")
        link = self.parse_url(link_str)
        date_str: str = soup.select_one("span[class=date-time]").get("title")
        date = self.parse_datetime(date_str)

        new_scrape_item = self.create_scrape_item(scrape_item, link, possible_datetime=date)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.strptime(date, "%A, %B %d, %Y %I:%M:%S%p %Z")
        return calendar.timegm(parsed_date.timetuple())
