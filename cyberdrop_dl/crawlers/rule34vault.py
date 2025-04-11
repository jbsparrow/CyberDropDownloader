from __future__ import annotations

import calendar
import datetime
import itertools
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager

CONTENT_SELECTOR = "div[class='box-grid ng-star-inserted']:first-child a[class='box ng-star-inserted']"
TITLE_SELECTOR = "div[class*=title]"
DATE_SELECTOR = 'div[class="posted-date-full text-secondary mt-4 ng-star-inserted"]'
VIDEO_SELECTOR = 'div[class="con-video ng-star-inserted"] > video > source'
IMAGE_SELECTOR = 'img[class*="img ng-star-inserted"]'


class Rule34VaultCrawler(Crawler):
    primary_base_domain = URL("https://rule34vault.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34vault", "Rule34Vault")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "post" in scrape_item.url.parts:
            return await self.file(scrape_item)
        if "playlists" in scrape_item.url.parts:
            return await self.playlist(scrape_item)
        await self.tag(scrape_item)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""

        # Broken
        raise NotImplementedError
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

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
        title: str = ""
        album_id = scrape_item.url.parts[-1]
        for page in itertools.count(1):
            url = scrape_item.url.with_query(page=page)
            has_content = False
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, url)

            if not title:
                title_str: str = soup.select_one(TITLE_SELECTOR).text  # type: ignore
                title = self.create_title(title_str, album_id)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, CONTENT_SELECTOR):
                has_content = True
                self.manager.task_group.create_task(self.run(new_scrape_item))

            if not has_content:
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if date_tag := soup.select_one(DATE_SELECTOR):
            scrape_item.possible_datetime = parse_datetime(date_tag.text)

        media_tag = soup.select_one(VIDEO_SELECTOR) or soup.select_one(IMAGE_SELECTOR)
        link_str: str = media_tag["src"]  # type: ignore
        for trash in (".small", ".thumbnail", ".720", ".hevc"):
            link_str = link_str.replace(trash, "")

        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%b %d, %Y, %I:%M:%S %p")
    return calendar.timegm(parsed_date.timetuple())
