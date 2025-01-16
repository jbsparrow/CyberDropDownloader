from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class Rule34XYZCrawler(Crawler):
    primary_base_domain = URL("https://rule34.xyz")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34.xyz", "Rule34XYZ")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "post" in scrape_item.url.parts:
            await self.file(scrape_item)
        else:
            await self.tag(scrape_item)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        title = self.create_title(scrape_item.url.parts[1])
        scrape_item.part_of_album = True

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select("a[class=boxInner]")
        for file_page in content:
            link_str: str = file_page.get("href")
            encoded = "%" in link_str
            if link_str.startswith("/"):
                link = self.primary_base_domain.joinpath(link_str[1:], encoded=encoded)
            else:
                link = URL(link_str, encoded=encoded)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()
        if not content:
            return

        if len(scrape_item.url.parts) > 2:
            page = int(scrape_item.url.parts[-1])
            next_page = scrape_item.url.with_path(f"/{scrape_item.url.parts[1]}/page/{page + 1}")
        else:
            next_page = scrape_item.url.with_path(f"/{scrape_item.url.parts[1]}/page/2")
        new_scrape_item = self.create_scrape_item(scrape_item, next_page, "")
        self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        date = self.parse_datetime(
            soup.select_one('div[class="posted ng-star-inserted"]').text.split("(")[1].split(")")[0],
        )
        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)

        image = soup.select_one('img[class*="img shadow-base"]')
        if image:
            link_str: str = image.get("src")
            encoded = "%" in link_str
            if link_str.startswith("/"):
                link = self.primary_base_domain.joinpath(link_str[1:], encoded=encoded)
            else:
                link = URL(link_str, encoded=encoded)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, new_scrape_item, filename, ext)

        video = soup.select_one("video source")
        if video:
            link_str: str = video.get("src")
            encoded = "%" in link_str
            if link_str.startswith("/"):
                link = self.primary_base_domain.joinpath(link_str[1:], encoded=encoded)
            else:
                link = URL(link_str, encoded=encoded)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date_time = datetime.datetime.strptime(date, "%b %d, %Y, %I:%M:%S %p")
        return calendar.timegm(date_time.timetuple())
