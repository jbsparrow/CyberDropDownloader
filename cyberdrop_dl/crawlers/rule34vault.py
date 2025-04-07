from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class Rule34VaultCrawler(Crawler):
    primary_base_domain = URL("https://rule34vault.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34vault", "Rule34Vault")

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

        ## Broken
        raise NotImplementedError
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(scrape_item.url.parts[1])
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select('a[class="box ng-star-inserted"]')
        if not content:
            return

        for file_page in content:
            link_str: str = file_page.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

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
        scrape_item.part_of_album = True
        scrape_item.album_id = scrape_item.url.parts[-1]

        title_str = soup.select_one("div[class*=title]").text
        title = self.create_title(title_str, scrape_item.album_id)

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select('a[class="box ng-star-inserted"]')
        if not content:
            return

        for file_page in content:
            link_str: str = file_page.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

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

        date_str = soup.select_one('div[class="posted-date-full text-secondary mt-4 ng-star-inserted"]').text
        date = self.parse_datetime(date_str)
        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)

        media_tag = soup.select_one('div[class="con-video ng-star-inserted"] > video > source') or soup.select_one(
            'img[class*="img ng-star-inserted"]'
        )
        link_str: str = (
            media_tag.get("src")
            .replace(".small", "")
            .replace(".thumbnail", "")
            .replace(".720", "")
            .replace(".hevc", "")
        )
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%b %d, %Y, %I:%M:%S %p")
        return calendar.timegm(parsed_date.timetuple())
