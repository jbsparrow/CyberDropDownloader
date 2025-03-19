from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_PROFILE
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class BunkrAlbumsIOCrawler(Crawler):
    primary_base_domain = URL("https://bunkr-albums.io/")
    skip_pre_check = True

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "bunkr-albums.io", "Bunkr-Albums.io")
        self.album_selector = "main div.auto-rows-max a"
        self.next_page_selector = "nav:last-of-type a.ic-arrow-right"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if not scrape_item.url.query.get("search"):  # Trying to scrape the root page is a bad idea
            raise ValueError

        await self.search(scrape_item)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes search results."""
        search_query = scrape_item.url.query.get("search")
        title = self.create_title(search_query)
        scrape_item.set_type(FILE_HOST_PROFILE, self.manager)
        async for soup in self.web_pager(scrape_item):
            albums = soup.select(self.album_selector)
            for album in albums:
                link_str: str = album.get("href")
                if not link_str:
                    continue
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
                self.handle_external_links(new_scrape_item)
                scrape_item.add_children()

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            current_page_number = int(page_url.query.get("page", 1))
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select(self.next_page_selector)
            yield soup
            if not next_page:
                break
            page_url_str: str = next_page[-1].get("href")
            page_url = self.parse_url(page_url_str)
            next_page_number = int(page_url.query.get("page", 1))
            if current_page_number >= next_page_number:
                break
