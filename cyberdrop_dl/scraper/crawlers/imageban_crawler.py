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


class ImageBanCrawler(Crawler):
    primary_base_domain = URL("https://www.imagebam.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imageban", "ImageBan")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        elif "c" in scrape_item.url.parts:
            await self.compilation(scrape_item)
        elif "show" in scrape_item.url.parts:
            await self.image(scrape_item)
        else:
            await self.handle_direct(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True

        title = self.create_title(
            soup.select_one("title").get_text().replace("Просмотр альбома: ", ""), scrape_item.album_id
        )
        content_block = soup.select_one('div[class="row text-center"]')
        images = content_block.select("a")
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        for image in images:
            link_str: str = image.get("href")
            if not link_str or "javascript:void(0)" in link_str:
                continue

            link = self.parse_url(link_str, scrape_item.url.with_path("/"))
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

        next_page = soup.select_one('a[class*="page-link next"]')
        if next_page:
            link_str: str = next_page.get("href")
            link = self.parse_url(link_str, scrape_item.url.with_path("/"))
            new_scrape_item = self.create_scrape_item(scrape_item, link)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def compilation(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a compilation."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(soup.select_one("blockquote").get_text(), scrape_item.url.parts[2])
        scrape_item.add_to_parent_title(title)
        content_block = soup.select("div[class=container-fluid]")[-1]
        images = content_block.select("img")
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        date = self.parse_datetime("-".join(scrape_item.url.parts[2:5]))

        for image in images:
            link_str: str = image.get("src")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        image = soup.select_one("img[id=img_main]")
        if not image:
            raise ScrapeError(422, origin=scrape_item)

        date = self.parse_datetime("-".join(scrape_item.url.parts[2:5]))
        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)
        link_str: str = image.get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d")
        return calendar.timegm(parsed_date.timetuple())
