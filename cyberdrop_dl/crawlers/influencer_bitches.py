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
    TITLE = "div.onlyf-model-info > h1"
    ALTERNATIVE_TITLE = "div.onlyf-leak-links a"
    VIDEOS = "div.onlyf-video-grid > div.onlyf-video-item"
    PICTURES = "a.onlyf-gallery-item:not(.onlyf-ad-item)"


_SELECTORS = Selectors()

PRIMARY_URL = AbsoluteHttpURL("https://influencerbitches.com")


class InfluencerBitchesCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Model": "/model/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "influencerbitches"
    FOLDER_DOMAIN: ClassVar[str] = "InfluencerBitches"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "model" in scrape_item.url.parts:
            return await self.model(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        title_tag = soup.select_one(_SELECTORS.TITLE) or soup.select_one(_SELECTORS.ALTERNATIVE_TITLE)
        assert title_tag
        title: str = title_tag.get_text(strip=True).replace("leaks", "").strip()
        title = self.create_title(title)
        scrape_item.setup_as_profile(title)

        for scrapper in (self.scrape_photos, self.scrape_videos):
            new_scrape_item = scrape_item.copy()
            await scrapper(new_scrape_item, soup)

    async def scrape_photos(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        album_id = scrape_item.url.name
        scrape_item.setup_as_album("Photos", album_id=album_id)
        results = await self.get_album_results(album_id)
        for a_tag in soup.select(_SELECTORS.PICTURES):
            link_str: str = css.select_one_get_attr(a_tag, "img", "data-full")
            link = self.parse_url(link_str)
            if self.check_album_results(link, results):
                continue
            web_url = self.parse_url(css.get_attr(a_tag, "href"))
            new_scrape_item = scrape_item.create_child(web_url)
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()

    async def scrape_videos(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> None:
        scrape_item.setup_as_album("Videos")
        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEOS, attribute="data-video-url"):
            if new_scrape_item.url.host == "bunkrrr.org":
                new_scrape_item.url = new_scrape_item.url.with_host("bunkr.fi")

            new_path = new_scrape_item.url.path.replace("/e/", "/f/", 1)
            new_scrape_item.url = new_scrape_item.url.with_path(new_path, keep_fragment=True, keep_query=True)
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()
