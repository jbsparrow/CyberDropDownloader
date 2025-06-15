from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedPaths
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


CONTENT_SELECTOR = "div[id=content] a"
TITLE_SELECTOR = "h2[class='font-semibold lg:text-2xl text-lg mb-2 mt-4']"
POST_CONTENT_SELECTOR = "div[class='flex justify-between items-center']"

PRIMARY_URL = AbsoluteHttpURL("https://fapello.su/")


class FapelloCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Individual Post": "/.../...",
        "Model": "/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = 'div[id="next_page"] a'
    DOMAIN: ClassVar[str] = "fapello"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(5, 1)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.name:
            scrape_item.url = scrape_item.url / ""
        if scrape_item.url.parts[-2].isdigit():
            return await self.post(scrape_item)

        await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = self.create_title(soup.select_one(TITLE_SELECTOR).get_text())
                scrape_item.setup_as_album(title)

            for post in soup.select(CONTENT_SELECTOR):
                link_str: str = post.get("href")
                if "javascript" in link_str:
                    video_tag = post.select_one("iframe")
                    link_str: str = video_tag.get("src")

                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.handle_external_links(new_scrape_item)
                scrape_item.add_children()

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        content = soup.select_one(POST_CONTENT_SELECTOR)
        if not content:
            raise ScrapeError(422)

        for _, link in self.iter_tags(soup, "img, source"):
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()
