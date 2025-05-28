from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedDomains, SupportedPaths
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://ibb.co")

IMAGE_PAGE_SELECTOR = "a[class*=image-container]"
ALBUM_PAGE_SELECTOR = "a[class='image-container --media']"
FIRST_PAGE_SELECTOR = "a[id=list-most-recent-link]"

IMAGE_SELECTOR = "div[id=image-viewer-container] img"
DATE_SELECTOR = "p[class*=description-meta] span"
ALBUM_TITLE_SELECTOR = "a[data-text=album-name]"

MAIN_HOST = "ibb.co"


class ImgBBCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Album": "/album/...", "Image": "/..."}
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "ibb.co", "imgbb.co"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a[data-pagination=next]"
    DOMAIN: ClassVar[str] = "imgbb"
    FOLDER_DOMAIN: ClassVar[str] = "ImgBB"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if is_cdn(scrape_item.url):
            image_id = scrape_item.url.parts[1]
            scrape_item.url = PRIMARY_URL / image_id

        scrape_item.url = scrape_item.url.with_host(MAIN_HOST)
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        title: str = ""

        async for soup in self.web_pager(scrape_item.url / "sub"):
            if not title:
                album_id = scrape_item.url.parts[2]
                title_portion = soup.select_one(ALBUM_TITLE_SELECTOR).get_text()
                title = self.create_title(title_portion, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)
                first_page_str: str = soup.select_one(FIRST_PAGE_SELECTOR).get("href")
                first_page = self.parse_url(first_page_str)

            for _, sub_album in self.iter_children(scrape_item, soup, ALBUM_PAGE_SELECTOR):
                self.manager.task_group.create_task(self.run(sub_album))

        async for soup in self.web_pager(first_page):
            for _, image in self.iter_children(scrape_item, soup, IMAGE_PAGE_SELECTOR):
                self.manager.task_group.create_task(self.run(image))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str: str = soup.select_one(IMAGE_SELECTOR).get("src")
        link = self.parse_url(link_str)
        date_str: str = soup.select_one(DATE_SELECTOR).get("title")
        scrape_item.possible_datetime = self.parse_datetime(date_str)

        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_name(scrape_item.url.name.replace(".md.", ".").replace(".th.", "."))
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())


async def is_cdn(url: URL) -> bool:
    """Determines if the url is a direct link or not."""
    return url.host == "i.ibb.co"
