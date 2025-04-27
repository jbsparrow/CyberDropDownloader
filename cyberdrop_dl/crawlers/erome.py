from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class Selectors:
    ALBUM = "a[class=album-link]"
    IMAGES = 'img[class="img-front lasyload"]'
    VIDEOS = "div[class=media-group] div[class=video-lg] video source"
    NEXT_PAGE = 'a[rel="next"]'


_SELECTORS = Selectors()


class EromeCrawler(Crawler):
    primary_base_domain = URL("https://www.erome.com")
    next_page_selector = _SELECTORS.NEXT_PAGE

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "erome", "Erome")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "a" in scrape_item.url.parts:
            return await self.album(scrape_item)
        await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = self.create_title(scrape_item.url.name)
                scrape_item.setup_as_profile(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title_portion = soup.select_one("title").text.rsplit(" - Porn")[0].strip()  # type: ignore
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
