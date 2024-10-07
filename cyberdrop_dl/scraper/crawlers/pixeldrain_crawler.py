from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionFailure
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem, FILE_HOST_ALBUM
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext
from cyberdrop_dl.clients.errors import ScrapeItemMaxChildrenReached

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class PixelDrainCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "pixeldrain", "PixelDrain")
        self.api_address = URL('https://pixeldrain.com/api/')
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)

        if "l" in scrape_item.url.parts:
            await self.folder(scrape_item)
        else:
            await self.file(scrape_item)

        await self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder"""
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0
        
        try:
            scrape_item.children_limit = self.manager.config_manager.settings_data['Download_Options']['maximum_number_of_children'][scrape_item.type]
        except (IndexError, TypeError):
            pass

        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(self.domain, self.api_address / "list" / scrape_item.url.parts[-1])

        title = await self.create_title(JSON_Resp['title'], scrape_item.url.parts[2], None)

        for file in JSON_Resp['files']:
            link = await self.create_download_link(file['id'])
            date = await self.parse_datetime(file['date_upload'].replace("T", " ").split(".")[0].strip("Z"))
            try:
                filename, ext = await get_filename_and_ext(file['name'])
            except NoExtensionFailure:
                if "image" in file["mime_type"] or "video" in file["mime_type"]:
                    filename, ext = await get_filename_and_ext(file['name'] + "." + file["mime_type"].split("/")[-1])
                else:
                    raise NoExtensionFailure()
            new_scrape_item = await self.create_scrape_item(scrape_item, link, title, True, None, date, add_parent = scrape_item.url)
            if not await self.check_album_results(link, results):
                await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.children += 1
            if scrape_item.children_limit:
                if scrape_item.children >= scrape_item.children_limit:
                    raise ScrapeItemMaxChildrenReached(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file"""
        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(self.domain,
                                                   self.api_address / "file" / scrape_item.url.parts[-1] / "info")

        link = await self.create_download_link(JSON_Resp['id'])
        date = await self.parse_datetime(JSON_Resp['date_upload'].replace("T", " ").split(".")[0])
        try:
            filename, ext = await get_filename_and_ext(JSON_Resp['name'])
        except NoExtensionFailure:
            if "text/plain" in JSON_Resp["mime_type"]:
                await scrape_item.add_to_parent_title(f"{JSON_Resp['name']} (Pixeldrain)")
                async with self.request_limiter:
                    text = await self.client.get_text(self.domain, self.api_address / "file" / scrape_item.url.parts[-1])
                lines = text.split("\n")
                for line in lines:
                    link = URL(line)
                    new_scrape_item = await self.create_scrape_item(scrape_item, link, "", False, None, date, add_parent = scrape_item.url)
                    await self.handle_external_links(new_scrape_item)
            elif "image" in JSON_Resp["mime_type"] or "video" in JSON_Resp["mime_type"]:
                filename, ext = await get_filename_and_ext(JSON_Resp['name'] + "." + JSON_Resp["mime_type"].split("/")[-1])
            else:
                raise NoExtensionFailure()
        new_scrape_item = await self.create_scrape_item(scrape_item, link, "", False, None, date)
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def parse_datetime(self, date: str) -> int:
        """Parses a datetime string into a unix timestamp"""
        try:
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%SZ")
        return calendar.timegm(date.timetuple())

    async def create_download_link(self, file_id: str) -> URL:
        """Creates a download link for a file"""
        link = (self.api_address / "file" / file_id).with_query('download')
        return link
