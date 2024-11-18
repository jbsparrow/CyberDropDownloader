from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class Rule34VaultCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34vault", "Rule34Vault")
        self.primary_base_url = URL("https://rule34vault.com")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "post" in scrape_item.url.parts:
            await self.file(scrape_item)
        elif "playlists" in scrape_item.url.parts:
            await self.playlist(scrape_item)
        else:
            await self.tag(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(scrape_item.url.parts[1], None, None)
        scrape_item.part_of_album = True
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select('a[class="box ng-star-inserted"]')
        for file_page in content:
            link = file_page.get("href")
            if link.startswith("/"):
                link = f"{self.primary_base_url}{link}"
            link = URL(link)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)
        if not content:
            return

        if "?page=" in scrape_item.url.parts[1]:
            page = int(scrape_item.url.parts[1].split("page=")[-1].split("&")[0])
            next_page = scrape_item.url.with_path(
                f"/{scrape_item.url.parts[1]}".replace(f"page={page}", f"page={page + 1}"),
                encoded=True,
            )
        else:
            next_page = scrape_item.url.with_path(f"/{scrape_item.url.parts[1]}?page=2", encoded=True)
        new_scrape_item = self.create_scrape_item(scrape_item, next_page, "")
        self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a playlist."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        title_str = soup.select_one("div[class*=title]").text
        scrape_item.part_of_album = True
        scrape_item.album_id = scrape_item.url.parts[-1]
        title = self.create_title(title_str, scrape_item.album_id, None)

        content_block = soup.select_one('div[class="box-grid ng-star-inserted"]')
        content = content_block.select('a[class="box ng-star-inserted"]')
        for file_page in content:
            link = file_page.get("href")
            if link.startswith("/"):
                link = f"{self.primary_base_url}{link}"
            link = URL(link)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)
        if not content:
            return

        if scrape_item.url.query:
            page = scrape_item.url.query.get("page")
            next_page = scrape_item.url.with_query({"page": int(page) + 1})
        else:
            next_page = scrape_item.url.with_query({"page": 2})
        new_scrape_item = self.create_scrape_item(scrape_item, next_page, "")
        self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        date = self.parse_datetime(
            soup.select_one('div[class="posted-date-full text-secondary mt-4 ng-star-inserted"]').text,
        )
        scrape_item.date = date

        image = soup.select_one('img[class*="img ng-star-inserted"]')
        if image:
            link = image.get("src").replace(".small", "").replace(".thumbnail", "")
            if link.startswith("/"):
                link = f"{self.primary_base_url}{link}"
            link = URL(link)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
        video = soup.select_one('div[class="con-video ng-star-inserted"] > video > source')
        if video:
            link = (
                video.get("src")
                .replace(".small", "")
                .replace(".thumbnail", "")
                .replace(".720", "")
                .replace(".hevc", "")
            )
            if link.startswith("/"):
                link = f"{self.primary_base_url}{link}"
            link = URL(link)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%b %d, %Y, %I:%M:%S %p")
        return calendar.timegm(date.timetuple())
