from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.data_structures.url_objects import FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


CHAPTER_SELECTOR = "li[class*=wp-manga-chapter] a"
IMAGE_SELECTOR = 'div[class="page-break no-gaps"] img'
SERIES_TITLE_SELECTOR = "div.post-title > h1"


class ToonilyCrawler(Crawler):
    primary_base_domain = URL("https://toonily.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "toonily", "Toonily")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "chapter" in scrape_item.url.name:
            return await self.chapter(scrape_item)
        if any(p in scrape_item.url.parts for p in ("webtoon", "series")):
            return await self.series(scrape_item)
        await self.handle_direct_link(scrape_item)

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a series."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        series_name = soup.select_one(SERIES_TITLE_SELECTOR).get_text(strip=True)  # type: ignore
        series_title = self.create_title(series_name)
        scrape_item.setup_as_profile(series_title)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, CHAPTER_SELECTOR):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        series_name, chapter_title = soup.select_one("title").get_text().split(" - ", 2)  # type: ignore
        if scrape_item.type != FILE_HOST_PROFILE:
            series_title = self.create_title(series_name)
            scrape_item.add_to_parent_title(series_title)

        scrape_item.setup_as_album(chapter_title)

        for script in soup.select("script"):
            if "datePublished" in (text := script.get_text()):
                date = text.split('datePublished":"')[1].split("+")[0]
                scrape_item.possible_datetime = self.parse_datetime(date)
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

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())
