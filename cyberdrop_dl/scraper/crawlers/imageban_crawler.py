from __future__ import annotations

import calendar
import contextlib
import datetime
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


class ImageBanCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imageban", "ImageBan")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        elif "c" in scrape_item.url.parts:
            await self.compilation(scrape_item)
        elif "show" in scrape_item.url.parts:
            await self.image(scrape_item)
        else:
            await self.handle_direct(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True

        title = self.create_title(
            soup.select_one("title").get_text().replace("Просмотр альбома: ", ""),
            scrape_item.album_id,
            None,
        )
        content_block = soup.select_one('div[class="row text-center"]')
        images = content_block.select("a")
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        for image in images:
            link_path = image.get("href")

            if "javascript:void(0)" in link_path:
                continue

            link = URL("https://" + scrape_item.url.host + link_path) if link_path.startswith("/") else URL(link_path)

            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

        next_page = soup.select_one('a[class*="page-link next"]')
        if next_page:
            link_path = next_page.get("href")
            link = URL("https://" + scrape_item.url.host + link_path) if link_path.startswith("/") else URL(link_path)
            new_scrape_item = self.create_scrape_item(scrape_item, link, "", True)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def compilation(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a compilation."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(soup.select_one("blockquote").get_text(), scrape_item.url.parts[2], None)
        scrape_item.add_to_parent_title(title)
        content_block = soup.select("div[class=container-fluid]")[-1]
        images = content_block.select("img")
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        for image in images:
            link = URL(image.get("src"))
            date = self.parse_datetime(f"{(link.parts[2])}-{(link.parts[3])}-{(link.parts[4])}")
            scrape_item.possible_datetime = date
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        date = self.parse_datetime(
            f"{(scrape_item.url.parts[2])}-{(scrape_item.url.parts[3])}-{(scrape_item.url.parts[4])}",
        )
        scrape_item.possible_datetime = date

        image = soup.select_one("img[id=img_main]")
        if image:
            link = URL(image.get("src"))
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%Y-%m-%d")
        return calendar.timegm(date.timetuple())
