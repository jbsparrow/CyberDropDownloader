from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from mediafire import MediaFireApi, api
from yarl import URL

from cyberdrop_dl.clients.errors import MediaFireError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


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
            await self.folder(scrape_item)
        else:
            await self.file(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder of media."""
        folder_key = scrape_item.url.parts[2]
        try:
            folder_details: dict[str, dict] = self.api.folder_get_info(folder_key=folder_key)
        except api.MediaFireApiError as e:
            raise MediaFireError(status=e.code, message=e.message, origin=scrape_item) from None

        title = self.create_title(folder_details["folder_info"]["name"], folder_key)
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
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
                )  # type: ignore
            except api.MediaFireApiError as e:
                raise MediaFireError(status=e.code, message=e.message, origin=scrape_item) from None

            files = folder_contents["folder_content"]["files"]

            for file in files:
                date = self.parse_datetime(file["created"])
                link_str = file["links"]["normal_download"]
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    possible_datetime=date,
                    add_parent=scrape_item.url,
                )
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            if not folder_contents["folder_content"]["more_chunks"] == "yes":
                break
            chunk += 1

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a single file."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_tag = soup.select_one("a[id=downloadButton]")
        if not link_tag:
            raise ScrapeError(422, origin=scrape_item)

        date_tag = soup.select("ul[class=details] li span")
        if date_tag:
            date = self.parse_datetime(date_tag[-1].get_text())
            scrape_item.possible_datetime = date
        link_str: str = link_tag.get("href")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed_date.timetuple())
