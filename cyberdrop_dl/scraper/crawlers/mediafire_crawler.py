from __future__ import annotations

import calendar
import contextlib
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from mediafire import MediaFireApi, api
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class MediaFireCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "mediafire", "mediafire")
        self.api = MediaFireApi()
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if "folder" in scrape_item.url.parts:
            await self.folder(scrape_item)
        else:
            await self.file(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder of media."""
        folder_key = scrape_item.url.parts[2]
        try:
            folder_details: dict[str, dict] = self.api.folder_get_info(folder_key=folder_key)
        except api.MediaFireApiError as e:
            raise ScrapeError(status=f"MF - {e.message}", origin=scrape_item) from None

        title = self.create_title(folder_details["folder_info"]["name"], folder_key, None)
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = self.manager.config_manager.settings_data["Download_Options"][
                "maximum_number_of_children"
            ][scrape_item.type]

        scrape_item.album_id = folder_key
        scrape_item.part_of_album = True

        chunk = 1
        chunk_size = 100
        while True:
            try:
                folder_contents: dict[str, dict] = self.api.folder_get_content(
                    folder_key=folder_key,
                    content_type="files",
                    chunk=chunk,
                    chunk_size=chunk_size,
                )
            except api.MediaFireApiError as e:
                raise ScrapeError(status=f"MF - {e.message}", origin=scrape_item) from None

            files = folder_contents["folder_content"]["files"]

            for file in files:
                date = self.parse_datetime(file["created"])
                link = URL(file["links"]["normal_download"])
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    True,
                    None,
                    date,
                    add_parent=scrape_item.url,
                )
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.children += 1
                if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                    raise MaxChildrenError(origin=scrape_item)

            if folder_contents["folder_content"]["more_chunks"] == "yes":
                chunk += 1
            else:
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a single file."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        date = self.parse_datetime(soup.select("ul[class=details] li span")[-1].get_text())
        scrape_item.possible_datetime = date
        link = URL(soup.select_one("a[id=downloadButton]").get("href"))
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(date.timetuple())
