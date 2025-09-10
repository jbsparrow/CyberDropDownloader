from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

ALBUM_SELECTOR = "main div.auto-rows-max a"

PRIMARY_URL = AbsoluteHttpURL("https://bunkr-albums.io/")


class BunkrAlbumsIOCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Search": "/s?search=..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "bunkr-albums.io"
    FOLDER_DOMAIN: ClassVar[str] = "Bunkr-Albums.io"
    NEXT_PAGE_SELECTOR: ClassVar[str] = "nav:last-of-type a.ic-arrow-right"
    SKIP_PRE_CHECK: ClassVar[bool] = True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.query.get("search"):  # Trying to scrape the root page is a bad idea
            return await self.search(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        search_query = scrape_item.url.query["search"]
        title = self.create_title(search_query)
        scrape_item.setup_as_profile(title)
        async for soup in self._pager(scrape_item):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, ALBUM_SELECTOR):
                self.handle_external_links(new_scrape_item)

    async def _pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            current_page_number = int(page_url.query.get("page") or 1)
            soup = await self.request_soup(page_url)
            next_page = soup.select(self.NEXT_PAGE_SELECTOR)
            yield soup
            if not next_page:
                break
            page_url_str: str = css.get_attr(next_page[-1], "href")
            page_url = self.parse_url(page_url_str)
            next_page_number = int(page_url.query.get("page") or 1)
            if current_page_number >= next_page_number:
                break
