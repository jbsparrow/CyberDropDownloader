from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.data_structures.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


IMAGES_SELECTOR = "div#gallery-view-content img"
IMAGE_SELECTOR = "img[id=img]"
ALBUM_TITLE_SELECTOR = "div[id=gallery-view] h1"


class ImgBoxCrawler(Crawler):
    primary_base_domain = URL("https://imgbox.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imgbox", "ImgBox")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        assert scrape_item.url.host
        if "t" in scrape_item.url.host or "_" in scrape_item.url.name:
            scrape_item.url = self.primary_base_domain / scrape_item.url.name.split("_")[0]

        elif "gallery/edit" in scrape_item.url.path:
            scrape_item.url = self.primary_base_domain / "g" / scrape_item.url.parts[-2]

        if "g" in scrape_item.url.parts:
            return await self.album(scrape_item)

        await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if "The specified gallery could not be found" in soup.text:
            raise ScrapeError(404)

        album_id = scrape_item.url.parts[2]

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        title = soup.select_one(ALBUM_TITLE_SELECTOR).get_text(strip=True).rsplit(" - ", 1)[0]  # type: ignore
        title = self.create_title(title, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        for link in soup.select(IMAGES_SELECTOR):
            link_str: str = link.get("src").replace("thumbs", "images").replace("_b", "_o")  # type: ignore
            link = self.parse_url(link_str)
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        link_str: str = soup.select_one(IMAGE_SELECTOR).get("src")  # type: ignore
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())
