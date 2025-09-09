from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
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
    _RATE_LIMIT = 5, 1

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
                title = self.create_title(css.select_one_get_text(soup, TITLE_SELECTOR))
                scrape_item.setup_as_album(title)

            for post in soup.select(CONTENT_SELECTOR):
                link_str: str = css.get_attr(post, "href")
                if "javascript" in link_str:
                    link_str = css.select_one_get_attr(post, "iframe", "src")

                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.handle_external_links(new_scrape_item)
                scrape_item.add_children()

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)

        content = css.select_one(soup, POST_CONTENT_SELECTOR)
        for _, link in self.iter_tags(content, "img, source"):
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()
