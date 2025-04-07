from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class OmegaScansCrawler(Crawler):
    primary_base_domain = URL("https://omegascans.org")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "omegascans", "OmegaScans")
        self.api_url = URL("https://api.omegascans.org/chapter/query")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "chapter" in scrape_item.url.name:
            await self.chapter(scrape_item)
        elif "series" in scrape_item.url.parts:
            await self.series(scrape_item)
        else:
            await self.handle_direct_link(scrape_item)

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        scrape_item.part_of_album = True

        scripts = soup.select("script")
        series_id = None
        for script in scripts:
            if "series_id" in script.get_text():
                series_id = script.get_text().split('series_id\\":')[1].split(",")[0]
                break

        if not series_id:
            raise ScrapeError(422, "Unable to parse series_id from html")

        page_number = 1
        number_per_page = 30
        while True:
            api_url = self.api_url.with_query(page=page_number, perPage=number_per_page, series_id=series_id)
            async with self.request_limiter:
                JSON_Obj = await self.client.get_json(self.domain, api_url)
            if not JSON_Obj:
                break

            for chapter in JSON_Obj["data"]:
                chapter_url = scrape_item.url / chapter["chapter_slug"]
                new_scrape_item = self.create_scrape_item(scrape_item, chapter_url, add_parent=scrape_item.url)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            if JSON_Obj["meta"]["current_page"] == JSON_Obj["meta"]["last_page"]:
                break
            page_number += 1

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if "This chapter is premium" in soup.get_text():
            raise ScrapeError(401, "This chapter is premium")

        scrape_item.part_of_album = True
        title_parts = soup.select_one("title").get_text().split(" - ")
        series_name = title_parts[0]
        chapter_title = title_parts[1]
        series_title = self.create_title(series_name)
        scrape_item.add_to_parent_title(series_title)
        scrape_item.add_to_parent_title(chapter_title)

        date = None
        date_str = soup.select('h2[class="font-semibold font-sans text-muted-foreground text-xs"]')[-1].get_text()
        try:
            date = self.parse_datetime_standard(date_str)
        except ValueError:
            scripts = soup.select("script")
            for script in scripts:
                if "created" in script.get_text():
                    date_str = script.get_text().split('created_at\\":\\"')[1].split(".")[0]
                    date = self.parse_datetime_other(date_str)
                    break

        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)
        images = soup.select("p[class*=flex] img")
        for image in images:
            link_str: str = image.get("src") or image.get("data-src")
            if not link_str:
                continue
            link = self.parse_url(link_str)
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_name(scrape_item.url.name)
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime_standard(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%m/%d/%Y")
        return calendar.timegm(parsed_date.timetuple())

    @staticmethod
    def parse_datetime_other(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())
