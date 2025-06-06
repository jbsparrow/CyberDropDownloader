from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

IMAGE_SELECTOR = "div[class=block-video] a img"
CONTENT_SELECTOR = "div[id=list_videos_common_videos_list_items] div a"

PRIMARY_URL = AbsoluteHttpURL("https://nudostar.tv/")


class NudoStarTVCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Model": "/models/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "li[class=next] a"
    DOMAIN: ClassVar[str] = "nudostar.tv"
    FOLDER_DOMAIN: ClassVar[str] = "NudoStarTV"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "models" not in scrape_item.url.parts:
            raise ValueError
        if scrape_item.url.name:
            scrape_item.url = scrape_item.url / ""
        if len(scrape_item.url.parts) > 4:
            return await self.image(scrape_item)
        await self.model(scrape_item)

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        title = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = self.create_title(css.select_one(soup, "title").get_text().split("/")[0])
                scrape_item.setup_as_album(title)

            if "Last OnlyFans Updates" in title or not soup.select_one(CONTENT_SELECTOR):
                raise ScrapeError(404)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, CONTENT_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        link_str = css.select_one_get_attr(soup, IMAGE_SELECTOR, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
