from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class RealBooruCrawler(Crawler):
    primary_base_domain = URL("https://realbooru.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "realbooru", "RealBooru")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        self.set_cookies()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        if "tags" in scrape_item.url.query_string:
            await self.tag(scrape_item)
        elif "id" in scrape_item.url.query_string:
            await self.file(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title_portion = scrape_item.url.query["tags"].strip()
        title = self.create_title(title_portion)
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True

        content = soup.select("div[class=items] div a")
        for file_page in content:
            link_str: str = file_page.get("href")
            link = self.parse_url(link_str)
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

        next_page = soup.select_one("a[alt=next]")
        if next_page:
            next_page_str: str = next_page.get("href")
            next_page = self.parse_url(next_page_str)
            new_scrape_item = self.create_scrape_item(scrape_item, next_page)
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        src_tag = soup.select_one("video source") or soup.select_one("img[id=image]")
        if not src_tag:
            raise ScrapeError(422, origin=scrape_item)
        link_str: str = src_tag.get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def set_cookies(self) -> None:
        """Sets the cookies for the client."""
        cookies = {"resize-original": "1"}
        self.update_cookies(cookies)
