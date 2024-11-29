from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, FILE_HOST_PROFILE, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class ToonilyCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "toonily", "Toonily")
        self.primary_base_domain = URL("https://toonily.com")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "chapter" in scrape_item.url.name:
            await self.chapter(scrape_item)
        elif "webtoon" in scrape_item.url.parts:
            await self.series(scrape_item)
        else:
            await self.handle_direct_link(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a series."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.type = FILE_HOST_PROFILE
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        chapters = soup.select("li[class*=wp-manga-chapter] a")
        for chapter in chapters:
            chapter_path: str = chapter.get("href")
            if not chapter_path:
                continue
            if chapter_path.endswith("/"):
                chapter_path = chapter_path[:-1]
            if chapter_path.startswith("/"):
                chapter_path = self.primary_base_domain / chapter_path[1:]
            else:
                chapter_path = URL(chapter_path)
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                chapter_path,
                "",
                True,
                add_parent=scrape_item.url,
            )
            self.manager.task_group.create_task(self.run(new_scrape_item))
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        title_parts = soup.select_one("title").get_text().split(" - ")
        series_name = title_parts[0]
        chapter_title = title_parts[1]
        series_title = self.create_title(series_name, None, None)
        scrape_item.add_to_parent_title(series_title)
        scrape_item.add_to_parent_title(chapter_title)

        scripts = soup.select("script")
        date = None
        for script in scripts:
            if "datePublished" in script.get_text():
                date = script.get_text().split('datePublished":"')[1].split("+")[0]
                date = self.parse_datetime(date)
                break

        scrape_item.possible_datetime = date if date else scrape_item.possible_datetime
        scrape_item.part_of_album = True

        images = soup.select('div[class="page-break no-gaps"] img')
        for image in images:
            link = image.get("data-src")
            if not link:
                continue
            link = URL(link)

            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_name(scrape_item.url.name)
        filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S")
        return calendar.timegm(date.timetuple())
