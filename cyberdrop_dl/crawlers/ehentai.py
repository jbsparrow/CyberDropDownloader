from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class EHentaiCrawler(Crawler):
    primary_base_domain = URL("https://e-hentai.org/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "e-hentai", "E-Hentai")

        self._warnings_set = False
        self.next_page_selector = "td[onclick='document.location=this.firstChild.href']:contains('>') a"
        self.next_page_attribute = "href"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "g" in scrape_item.url.parts:
            await self.album(scrape_item)
        elif "s" in scrape_item.url.parts:
            await self.image(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        if not self._warnings_set:
            await self.set_no_warnings(scrape_item)

        title = date = None
        gallery_id = scrape_item.url.parts[2]
        scrape_item.url = scrape_item.url.with_query(None)
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        async for soup in self.web_pager(scrape_item):
            if not title:
                title = self.create_title(soup.select_one("h1[id=gn]").get_text())
                date = self.parse_datetime(soup.select_one("td[class=gdt2]").get_text())

            images = soup.select("div#gdt.gt200 a")
            for image in images:
                link_str: str = image.get("href")
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    part_of_album=True,
                    album_id=gallery_id,
                    possible_datetime=date,
                    add_parent=scrape_item.url,
                )

                await self.image(new_scrape_item)
                scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        image = soup.select_one("img[id=img]")
        link_str: str = image.get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        custom_filename, _ = get_filename_and_ext(f"{scrape_item.url.name}{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def set_no_warnings(self, scrape_item: ScrapeItem) -> None:
        """Sets the no warnings cookie."""
        async with self.request_limiter:
            url = scrape_item.url.update_query(nw="session")
            await self.client.get_soup(self.domain, url, origin=scrape_item)
        self._warnings_set = True

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        if date.count(":") == 1:
            date = date + ":00"
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(self.next_page_selector)
            yield soup
            if not next_page:
                break
            page_url_str: str = next_page.get(self.next_page_attribute)
            page_url = self.parse_url(page_url_str)
