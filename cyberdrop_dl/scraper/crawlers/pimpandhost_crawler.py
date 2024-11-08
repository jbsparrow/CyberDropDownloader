from __future__ import annotations

import calendar
import contextlib
from datetime import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class PimpAndHostCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pimpandhost", "PimpAndHost")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "album" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.image(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True

        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        title = self.create_title(
            soup.select_one("span[class=author-header__album-name]").get_text(),
            scrape_item.album_id,
            None,
        )
        date = soup.select_one("span[class=date-time]").get("title")
        date = self.parse_datetime(date)

        files = soup.select('a[class*="image-wrapper center-cropped im-wr"]')
        for file in files:
            link = URL(file.get("href"))
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                title,
                True,
                None,
                date,
                add_parent=scrape_item.url,
            )
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

        next_page = soup.select_one("li[class=next] a")
        if next_page:
            next_page = next_page.get("href")
            if next_page.startswith("/"):
                next_page = URL("https://pimpandhost.com" + next_page)
            new_scrape_item = self.create_scrape_item(scrape_item, next_page, "", True, None, date)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link = soup.select_one(".main-image-wrapper")
        link = link.get("data-src")
        link = URL("https:" + link) if link.startswith("//") else URL(link)

        date = soup.select_one("span[class=date-time]").get("title")
        date = self.parse_datetime(date)

        new_scrape_item = self.create_scrape_item(scrape_item, link, "", True, None, date)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.strptime(date, "%A, %B %d, %Y %I:%M:%S%p %Z")
        return calendar.timegm(date.timetuple())
