from __future__ import annotations

import calendar
import datetime
import json
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import DownloadError, NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class PixelDrainCrawler(Crawler):
    primary_base_domain = URL("https://pixeldrain.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pixeldrain", "PixelDrain")
        self.api_address = URL("https://pixeldrain.com/api/")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "l" in scrape_item.url.parts:
            await self.folder(scrape_item)
        else:
            await self.file(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a folder."""
        album_id = scrape_item.url.parts[2]
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True
        results = await self.get_album_results(album_id)
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        async with self.request_limiter:
            JSON_Resp = await self.client.get_json(
                self.domain,
                self.api_address / "list" / scrape_item.url.parts[-1],
                origin=scrape_item,
            )

        title = self.create_title(JSON_Resp["title"], scrape_item.url.parts[2], None)

        for file in JSON_Resp["files"]:
            link = await self.create_download_link(file["id"])
            date = self.parse_datetime(file["date_upload"].replace("T", " ").split(".")[0].strip("Z"))
            try:
                filename, ext = get_filename_and_ext(file["name"])
            except NoExtensionError:
                if "image" in file["mime_type"] or "video" in file["mime_type"]:
                    filename, ext = get_filename_and_ext(file["name"] + "." + file["mime_type"].split("/")[-1])
                else:
                    raise
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                new_title_part=title,
                part_of_album=True,
                possible_datetime=date,
                add_parent=scrape_item.url,
            )
            if not self.check_album_results(link, results):
                await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        if await self.check_complete_from_referer(scrape_item):
            return
        try:
            async with self.request_limiter:
                JSON_Resp = await self.client.get_json(
                    self.domain,
                    self.api_address / "file" / scrape_item.url.parts[-1] / "info",
                    origin=scrape_item,
                )
        except DownloadError as e:
            if e.status != 404:
                raise
            return await self.filesystem(scrape_item)

        link = await self.create_download_link(JSON_Resp["id"])
        date = self.parse_datetime(JSON_Resp["date_upload"].replace("T", " ").split(".")[0])
        filename = ext = None
        try:
            filename, ext = get_filename_and_ext(JSON_Resp["name"])
        except NoExtensionError:
            if "text/plain" in JSON_Resp["mime_type"]:
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    scrape_item.url,
                    new_title_part=f"{JSON_Resp['name']} (Pixeldrain)",
                    possible_datetime=date,
                    add_parent=scrape_item.url,
                )
                return await self.text(new_scrape_item)

            elif "image" in JSON_Resp["mime_type"] or "video" in JSON_Resp["mime_type"]:
                filename, ext = get_filename_and_ext(
                    JSON_Resp["name"] + "." + JSON_Resp["mime_type"].split("/")[-1],
                )
            else:
                raise

        new_scrape_item = self.create_scrape_item(scrape_item, link, possible_datetime=date)
        await self.handle_file(link, new_scrape_item, filename, ext)

    async def text(self, scrape_item: ScrapeItem):
        async with self.request_limiter:
            text = await self.client.get_text(
                self.domain,
                self.api_address / "file" / scrape_item.url.parts[-1],
                origin=scrape_item,
            )
        lines = text.split("\n")
        for line in lines:
            link = URL(line)
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                add_parent=scrape_item.url,
            )
            self.handle_external_links(new_scrape_item)

    async def filesystem(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(
                self.domain,
                scrape_item.url,
                origin=scrape_item,
            )
        meta_tag: str = soup.select_one('meta[property="og:type"]').get("content")
        filename: str = soup.select_one('meta[property="og:title"]').get("content")
        link = None
        if "video" in meta_tag:
            link = soup.select_one('meta[property="og:video"]').get("content")
        elif "image" in meta_tag:
            link = soup.select_one('meta[property="og:image"]').get("content")

        if not link or "filesystem" not in link:
            raise ScrapeError(422, origin=scrape_item)

        script_tag: str = soup.select_one('script:contains("window.initial_node")').string
        start_sentence = "window.initial_node ="
        end_sentence = "window.user = "
        start_index = script_tag.find(start_sentence) + len(start_sentence)
        end_index = script_tag.find(end_sentence)
        extracted_json_str = script_tag[start_index:end_index].strip().removesuffix(";")
        json_data = json.loads(extracted_json_str)
        date_str: str = json_data["path"][0]["created"]
        date = self.parse_datetime(date_str.replace("T", " ").split(".")[0])
        link = URL(link)
        filename, ext = get_filename_and_ext(filename)
        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)
        await self.handle_file(link, new_scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def create_download_link(self, file_id: str) -> URL:
        """Creates a download link for a file."""
        return (self.api_address / "file" / file_id).with_query("download")

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        try:
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%SZ")
        return calendar.timegm(date.timetuple())
