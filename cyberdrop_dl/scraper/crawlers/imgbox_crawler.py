from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeFailure
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem, FILE_HOST_ALBUM
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext
from cyberdrop_dl.clients.errors import ScrapeItemMaxChildrenReached

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from bs4 import BeautifulSoup


class ImgBoxCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "imgbox", "ImgBox")
        self.primary_base_domain = URL("https://imgbox.com")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        if "t" in scrape_item.url.host or "_" in scrape_item.url.name:
            scrape_item.url = self.primary_base_domain / scrape_item.url.name.split("_")[0]

        if "gallery/edit" in str(scrape_item.url):
            scrape_item.url = self.primary_base_domain / "g" / scrape_item.url.parts[-2]

        if "g" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.image(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album"""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url, origin=scrape_item)

        if "The specified gallery could not be found" in soup.text:
            raise ScrapeFailure(404, f"Gallery not found: {scrape_item.url}", origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True

        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0
        
        try:
            scrape_item.children_limit = self.manager.config_manager.settings_data['Download_Options']['maximum_number_of_children'][scrape_item.type]
        except (IndexError, TypeError):
            pass

        title = await self.create_title(
            soup.select_one("div[id=gallery-view] h1").get_text().strip().rsplit(" - ", 1)[0], scrape_item.album_id,
            None)

        scrape_item.part_of_album = True
        await scrape_item.add_to_parent_title(title)

        images = soup.find('div', attrs={'id': 'gallery-view-content'})
        images = images.findAll("img")
        for link in images:
            link = URL(link.get('src').replace("thumbs", "images").replace("_b", "_o"))
            filename, ext = await get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.children += 1
            if scrape_item.children_limit:
                if scrape_item.children >= scrape_item.children_limit:
                    raise ScrapeItemMaxChildrenReached(origin = scrape_item)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image"""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_BS4(self.domain, scrape_item.url, origin=scrape_item)

        image = URL(soup.select_one("img[id=img]").get('src'))
        filename, ext = await get_filename_and_ext(image.name)
        await self.handle_file(image, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    async def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp"""
        date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(date.timetuple())
