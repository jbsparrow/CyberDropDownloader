from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

ALBUM_SELECTOR = "main div.auto-rows-max a"


class BunkrAlbumsIOCrawler(Crawler):
    primary_base_domain = URL("https://bunkr-albums.io/")
    next_page_selector = "nav:last-of-type a.ic-arrow-right"
    skip_pre_check = True

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "bunkr-albums.io", "Bunkr-Albums.io")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if scrape_item.url.query.get("search"):  # Trying to scrape the root page is a bad idea
            return await self.search(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        """Scrapes search results."""
        search_query = scrape_item.url.query["search"]
        title = self.create_title(search_query)
        scrape_item.setup_as_profile(title)
        async for soup in self.web_pager(scrape_item):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, ALBUM_SELECTOR):
                self.handle_external_links(new_scrape_item)

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            current_page_number = int(page_url.query.get("page") or 1)
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
            next_page = soup.select(self.next_page_selector)
            yield soup
            if not next_page:
                break
            page_url_str: str = next_page[-1].get("href")  # type: ignore
            page_url = self.parse_url(page_url_str)
            next_page_number = int(page_url.query.get("page") or 1)
            if current_page_number >= next_page_number:
                break
