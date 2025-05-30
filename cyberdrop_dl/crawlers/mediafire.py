from __future__ import annotations

import calendar
import datetime
import itertools
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from mediafire import MediaFireApi, api
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import MediaFireError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

DOWNLOAD_BUTTON_SELECTOR = "a[id=downloadButton]"
DATE_SELECTOR = "ul[class=details] li span"


class MediaFireCrawler(Crawler):
    primary_base_domain = URL("https://www.mediafire.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "mediafire", "mediafire")
        self.api = MediaFireApi()
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "folder" in scrape_item.url.parts:
            return await self.folder(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder of media."""
        folder_key = scrape_item.url.parts[2]
        try:
            folder_details: dict[str, dict] = self.api.folder_get_info(folder_key=folder_key)  # type: ignore
        except api.MediaFireApiError as e:
            raise MediaFireError(status=e.code, message=e.message) from None

        title = self.create_title(folder_details["folder_info"]["name"], folder_key)
        scrape_item.setup_as_album(title)

        for chunk in itertools.count(1):
            try:
                folder_contents: dict = self.api.folder_get_content(folder_key, "files", chunk=chunk, chunk_size=100)  # type: ignore
            except api.MediaFireApiError as e:
                raise MediaFireError(status=e.code, message=e.message) from None

            for file in folder_contents["folder_content"]["files"]:
                date = self.parse_datetime(file["created"])
                link = self.parse_url(file["links"]["normal_download"])
                new_scrape_item = scrape_item.create_child(link, new_title_part=title, possible_datetime=date)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            if not folder_contents["folder_content"]["more_chunks"] == "yes":
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a single file."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        link_tag = soup.select_one(DOWNLOAD_BUTTON_SELECTOR)
        if not link_tag:
            if "Something appears to be missing" in soup.get_text():
                raise ScrapeError(410)
            raise ScrapeError(422)

        scrape_item.possible_datetime = self.parse_datetime(soup.select(DATE_SELECTOR)[-1].get_text())
        link_str: str = link_tag.get("href")  # type: ignore
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())
