from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    ALBUM = "a[class=album-link]"
    IMAGES = 'img[class="img-front lasyload"]'
    VIDEOS = "div[class=media-group] div[class=video-lg] video source"
    NEXT_PAGE = 'a[rel="next"]'


_SELECTORS = Selectors()

PRIMARY_URL = AbsoluteHttpURL("https://www.erome.com")


class EromeCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/...",
        "Profile": "/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    DOMAIN: ClassVar[str] = "erome"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "a" in scrape_item.url.parts:
            return await self.album(scrape_item)
        await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = self.create_title(scrape_item.url.name)
                scrape_item.setup_as_profile(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        title_portion = css.select_one_get_text(soup, "title").rsplit(" - Porn")[0].strip()
        if not title_portion:
            title_portion = scrape_item.url.name

        title = self.create_title(title_portion, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        attributes = ("data-src", "src")
        selectors = (_SELECTORS.IMAGES, _SELECTORS.VIDEOS)
        for selector, attribute in zip(selectors, attributes, strict=True):
            for _, link in self.iter_tags(soup, selector, attribute, results=results):
                filename, ext = self.get_filename_and_ext(link.name)
                await self.handle_file(link, scrape_item, filename, ext)
                scrape_item.add_children()
