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


class Rule34VaultCrawler(Crawler):
    primary_base_domain = URL("https://rule34vault.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34vault", "Rule34Vault")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "post" in scrape_item.url.parts:
            await self.file(scrape_item)
        elif "playlists" in scrape_item.url.parts:
            await self.playlist(scrape_item)
        else:
            await self.tag(scrape_item)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(scrape_item.url.parts[1])
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select('a[class="box ng-star-inserted"]')
        for file_page in content:
            link_str: str = file_page.get("href")
            encoded = "%" in link_str
            if link_str.startswith("/"):
                link = self.primary_base_domain.joinpath(link_str[1:], encoded=encoded)
            else:
                link = URL(link_str, encoded=encoded)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()
        if not content:
            return

        page = scrape_item.url.query.get("page", 1)
        page_number = int(page)
        next_page = scrape_item.url.with_query(page=page_number + 1)

        new_scrape_item = self.create_scrape_item(scrape_item, next_page)
        self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a playlist."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        title_str = soup.select_one("div[class*=title]").text
        scrape_item.part_of_album = True
        scrape_item.album_id = scrape_item.url.parts[-1]
        title = self.create_title(title_str, scrape_item.album_id)

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select('a[class="box ng-star-inserted"]')
        for file_page in content:
            link_str: str = file_page.get("href")
            encoded = "%" in link_str
            if link_str.startswith("/"):
                link = self.primary_base_domain.joinpath(link_str[1:], encoded=encoded)
            else:
                link = URL(link_str, encoded=encoded)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()
        if not content:
            return

        page = scrape_item.url.query.get("page", 1)
        page_number = int(page)
        next_page = scrape_item.url.with_query(page=page_number + 1)
        new_scrape_item = self.create_scrape_item(scrape_item, next_page)
        self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        date = self.parse_datetime(
            soup.select_one('div[class="posted-date-full text-secondary mt-4 ng-star-inserted"]').text,
        )
        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)

        image = soup.select_one('img[class*="img ng-star-inserted"]')
        if image:
            link_str: str = image.get("src").replace(".small", "").replace(".thumbnail", "")
            encoded = "%" in link_str
            if link_str.startswith("/"):
                link = self.primary_base_domain.joinpath(link_str[1:], encoded=encoded)
            else:
                link = URL(link_str, encoded=encoded)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, new_scrape_item, filename, ext)
        video = soup.select_one('div[class="con-video ng-star-inserted"] > video > source')
        if video:
            link_str = (
                video.get("src")
                .replace(".small", "")
                .replace(".thumbnail", "")
                .replace(".720", "")
                .replace(".hevc", "")
            )
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
        parsed_date = datetime.datetime.strptime(date, "%b %d, %Y, %I:%M:%S %p")
        return calendar.timegm(parsed_date.timetuple())
