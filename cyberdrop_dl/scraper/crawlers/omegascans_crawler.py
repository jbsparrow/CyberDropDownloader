from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class OmegaScansCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "omegascans", "OmegaScans")
        self.primary_base_domain = URL("https://omegascans.org")
        self.api_url = "https://api.omegascans.org/chapter/query?page={}&perPage={}&series_id={}"
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "chapter" in scrape_item.url.name:
            await self.chapter(scrape_item)
        elif "series" in scrape_item.url.parts:
            await self.series(scrape_item)
        else:
            await self.handle_direct_link(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        scripts = soup.select("script")
        series_id = None
        for script in scripts:
            if "series_id" in script.get_text():
                series_id = script.get_text().split('series_id\\":')[1].split(",")[0]
                break

        if not series_id:
            raise ScrapeError(404, "series_id not found", origin=ScrapeItem)

        page_number = 1
        number_per_page = 30
        while True:
            api_url = URL(self.api_url.format(page_number, number_per_page, series_id))
            async with self.request_limiter:
                JSON_Obj = await self.client.get_json(self.domain, api_url, origin=scrape_item)
            if not JSON_Obj:
                break

            for chapter in JSON_Obj["data"]:
                chapter_url = scrape_item.url / chapter["chapter_slug"]
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    chapter_url,
                    "",
                    True,
                    add_parent=scrape_item.url,
                )
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.children += 1
                if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                    raise MaxChildrenError(origin=scrape_item)

            if JSON_Obj["meta"]["current_page"] == JSON_Obj["meta"]["last_page"]:
                break
            page_number += 1

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        if "This chapter is premium" in soup.get_text():
            log("Scrape Failed: This chapter is premium", 40)
            raise ScrapeError(401, "This chapter is premium", origin=scrape_item)

        title_parts = soup.select_one("title").get_text().split(" - ")
        series_name = title_parts[0]
        chapter_title = title_parts[1]
        series_title = self.create_title(series_name, None, None)
        scrape_item.add_to_parent_title(series_title)
        scrape_item.add_to_parent_title(chapter_title)

        date = soup.select('h2[class="font-semibold font-sans text-muted-foreground text-xs"]')[-1].get_text()
        try:
            date = self.parse_datetime_standard(date)
        except ValueError:
            scripts = soup.select("script")
            for script in scripts:
                if "created" in script.get_text():
                    date = script.get_text().split('created_at\\":\\"')[1].split(".")[0]
                    date = self.parse_datetime_other(date)
                    break

        scrape_item.possible_datetime = date
        scrape_item.part_of_album = True

        images = soup.select("p[class*=flex] img")
        for image in images:
            link = image.get("src")
            if not link:
                link = image.get("data-src")
                if not link:
                    continue
            link = URL(link)

            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_name(scrape_item.url.name)
        filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime_standard(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%m/%d/%Y")
        return calendar.timegm(date.timetuple())

    @staticmethod
    def parse_datetime_other(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S")
        return calendar.timegm(date.timetuple())
