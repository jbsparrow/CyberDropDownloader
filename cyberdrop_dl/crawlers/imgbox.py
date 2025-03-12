from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager


class ImgBoxCrawler(Crawler):
    primary_base_domain = URL("https://imgbox.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imgbox", "ImgBox")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "t" in scrape_item.url.host or "_" in scrape_item.url.name:
            scrape_item.url = self.primary_base_domain / scrape_item.url.name.split("_")[0]

        if "gallery/edit" in str(scrape_item.url):
            scrape_item.url = self.primary_base_domain / "g" / scrape_item.url.parts[-2]

        if "g" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        if "The specified gallery could not be found" in soup.text:
            raise ScrapeError(404, origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        title = self.create_title(
            soup.select_one("div[id=gallery-view] h1").get_text().strip().rsplit(" - ", 1)[0], scrape_item.album_id
        )

        scrape_item.part_of_album = True
        scrape_item.add_to_parent_title(title)

        images = soup.find("div", attrs={"id": "gallery-view-content"})
        images: list[Tag] = images.findAll("img")
        for link in images:
            link_str: str = link.get("src").replace("thumbs", "images").replace("_b", "_o")
            link = self.parse_url(link_str)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_str: str = soup.select_one("img[id=img]").get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())
