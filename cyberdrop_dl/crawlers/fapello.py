from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


CONTENT_SELECTOR = "div[id=content] a"
TITLE_SELECTOR = "h2[class='font-semibold lg:text-2xl text-lg mb-2 mt-4']"
POST_CONTENT_SELECTOR = "div[class='flex justify-between items-center']"


class FapelloCrawler(Crawler):
    primary_base_domain = URL("https://fapello.su/")
    next_page_selector = 'div[id="next_page"] a'

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "fapello", "Fapello")
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if scrape_item.url.name:
            scrape_item.url = scrape_item.url / ""
        if scrape_item.url.parts[-2].isdigit():
            return await self.post(scrape_item)

        await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""

        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = self.create_title(soup.select_one(TITLE_SELECTOR).get_text())  # type: ignore
                scrape_item.setup_as_album(title)

            for post in soup.select(CONTENT_SELECTOR):
                link_str: str = post.get("href")  # type: ignore
                if "javascript" in link_str:
                    video_tag = post.select_one("iframe")
                    link_str: str = video_tag.get("src")  # type: ignore

                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.handle_external_links(new_scrape_item)
                scrape_item.add_children()

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        """Scrapes apost."""

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        content = soup.select_one(POST_CONTENT_SELECTOR)
        if not content:
            raise ScrapeError(422)

        for _, link in self.iter_tags(soup, "img, source"):
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()
