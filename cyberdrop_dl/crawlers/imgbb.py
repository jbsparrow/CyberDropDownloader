from __future__ import annotations

import calendar
import datetime
import re
from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


IMAGE_PAGE_SELECTOR = "a[class*=image-container]"
ALBUM_PAGE_SELECTOR = "a[class='image-container --media']"
FIRST_PAGE_SELECTOR = "a[id=list-most-recent-link]"

IMAGE_SELECTOR = "div[id=image-viewer-container] img"
DATE_SELECTOR = "p[class*=description-meta] span"


class ImgBBCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"imgbb": ["ibb.co", "imgbb.co"]}
    primary_base_domain = URL("https://ibb.co")
    next_page_selector = "a[data-pagination=next]"

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "ImgBB")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        if await self.check_direct_link(scrape_item.url):
            image_id = scrape_item.url.parts[1]
            scrape_item.url = self.primary_base_domain / image_id

        scrape_item.url = self.primary_base_domain / scrape_item.url.path[1:]
        if "album" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        title: str = ""

        async for soup in self.web_pager(scrape_item.url / "sub"):
            if not title:
                album_id = scrape_item.url.parts[2]
                title_portion = soup.select_one("a[data-text=album-name]").get_text()
                title = self.create_title(title_portion, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)
                first_page_str: str = soup.select_one(FIRST_PAGE_SELECTOR).get("href")
                first_page = self.parse_url(first_page_str)

            for sub_album in soup.select(ALBUM_PAGE_SELECTOR):
                link_str: str = sub_album.get("href")  # type: ignore
                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

        async for soup in self.web_pager(first_page):
            for image in soup.select(IMAGE_PAGE_SELECTOR):
                link_str: str = image.get("href")  # type: ignore
                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_str: str = soup.select_one(IMAGE_SELECTOR).get("src")  # type: ignore
        link = self.parse_url(link_str)
        date_str: str = soup.select_one(DATE_SELECTOR).get("title")  # type: ignore
        date = self.parse_datetime(date_str)
        scrape_item.possible_datetime = date

        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_name(scrape_item.url.name.replace(".md.", ".").replace(".th.", "."))
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())

    @staticmethod
    async def check_direct_link(url: URL) -> bool:
        """Determines if the url is a direct link or not."""
        mapping_direct = (r"i.ibb.co",)
        return any(re.search(domain, str(url)) for domain in mapping_direct)
