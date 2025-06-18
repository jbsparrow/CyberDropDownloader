from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import FILE_HOST_PROFILE, AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


CHAPTER_SELECTOR = "li[class*=wp-manga-chapter] a"
IMAGE_SELECTOR = 'div[class="page-break no-gaps"] img'
SERIES_TITLE_SELECTOR = "div.post-title > h1"
PRIMARY_URL = AbsoluteHttpURL("https://toonily.com")


class ToonilyCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Chapter": "/webtoon/.../...",
        "Webtoon": "/webtoon/...",
        "Direct links": "",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "toonily"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "chapter" in scrape_item.url.name:
            return await self.chapter(scrape_item)
        if any(p in scrape_item.url.parts for p in ("webtoon", "series")):
            return await self.series(scrape_item)
        await self.handle_direct_link(scrape_item)

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        series_name = css.select_one_get_text(soup, SERIES_TITLE_SELECTOR)
        series_title = self.create_title(series_name)
        scrape_item.setup_as_profile(series_title)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, CHAPTER_SELECTOR):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        series_name, chapter_title = css.select_one_get_text(soup, "title").split(" - ", 2)
        if scrape_item.type != FILE_HOST_PROFILE:
            series_title = self.create_title(series_name)
            scrape_item.add_to_parent_title(series_title)

        scrape_item.setup_as_album(chapter_title)

        for script in soup.select("script"):
            if "datePublished" in (text := script.get_text()):
                date_str = text.split('datePublished":"')[1].split("+")[0]
                scrape_item.possible_datetime = self.parse_date(date_str)
                break

        for _, link in self.iter_tags(soup, IMAGE_SELECTOR, "data-src"):
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_query(None)
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)
