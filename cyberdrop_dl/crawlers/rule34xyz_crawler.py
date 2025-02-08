from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
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
        scrape_item.part_of_album = True
        title = self.create_title(scrape_item.url.parts[1])

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select("a[class=boxInner]")
        if not content:
            return

        for file_page in content:
            link_str: str = file_page.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

        page = 2
        if len(scrape_item.url.parts) > 2:
            page = int(scrape_item.url.parts[-1])
        next_page = scrape_item.url.with_path("/") / scrape_item.url.parts[1] / "page" / f"{page + 1}"
        new_scrape_item = self.create_scrape_item(scrape_item, next_page)
        self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        date_str: str = soup.select_one('div[class="posted ng-star-inserted"]').text.split("(")[1].split(")")[0]
        date = self.parse_datetime(date_str)
        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)

        media_tag = soup.select_one("video source") or soup.select_one('img[class*="img shadow-base"]')
        if not media_tag:
            raise ScrapeError(422, origin=scrape_item)

        link_str: str = media_tag.get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%b %d, %Y, %I:%M:%S %p")
        return calendar.timegm(parsed_date.timetuple())
