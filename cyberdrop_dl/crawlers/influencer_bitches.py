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
    TITLE = "div.onlyf-model-info > h1"
    ALTERNATIVE_TITLE = "div.onlyf-leak-links a"
    VIDEOS = "div.onlyf-video-grid > div.onlyf-video-item"
    PICTURES = "div.onlyf-image-container > img"


_SELECTORS = Selectors()


class InfluencerBitchesCrawler(Crawler):
    primary_base_domain = URL("https://influencerbitches.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "influencerbitches", "InfluencerBitches")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "model" in scrape_item.url.parts:
            return await self.model(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title: str = soup.select_one(_SELECTORS.TITLE).get_text(strip=True)
        if not title:
            title = soup.select_one(_SELECTORS.ALTERNATIVE_TITLE).get_text().replace("leaks", "").strip()
        title = self.create_title(title)
        scrape_item.setup_as_profile(title)

        await self.scrape_pictures(scrape_item, soup)
        await self.scrape_videos(scrape_item, soup)

    async def scrape_pictures(self, scrape_item, soup):
        scrape_item_copy = scrape_item.copy()
        scrape_item_copy.setup_as_album("Photos")
        for _, new_scrape_item in self.iter_children(
            scrape_item_copy, soup, _SELECTORS.PICTURES, attribute="data-full"
        ):
            filename, ext = self.get_filename_and_ext(new_scrape_item.url.name)
            if not await self.check_complete_from_referer(new_scrape_item):
                await self.handle_file(new_scrape_item.url, new_scrape_item, filename, ext)
                scrape_item_copy.add_children()

    async def scrape_videos(self, scrape_item, soup):
        scrape_item_copy = scrape_item.copy()
        scrape_item_copy.setup_as_album("Videos")
        for _, new_scrape_item in self.iter_children(
            scrape_item_copy, soup, _SELECTORS.VIDEOS, attribute="data-video-url"
        ):
            if new_scrape_item.url.host == "bunkrrr.org":
                new_scrape_item.url = new_scrape_item.url.with_host("bunkr.fi")
            new_scrape_item.url = new_scrape_item.url.with_path(new_scrape_item.url.path.replace("/e/", "/f/", 1))
            if not await self.check_complete_from_referer(new_scrape_item.url):
                self.handle_external_links(new_scrape_item)
                scrape_item_copy.add_children()
