from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter
from mediafire import MediaFireApi, api

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import MediaFireError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

DOWNLOAD_BUTTON_SELECTOR = "a[id=downloadButton]"
DATE_SELECTOR = "ul[class=details] li span"
PRIMARY_URL = AbsoluteHttpURL("https://www.mediafire.com/")


class MediaFireCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": "/file/...",
        "Folder": "/folder/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "mediafire"

    def __post_init__(self) -> None:
        self.api = MediaFireApi()
        self.request_limiter = AsyncLimiter(5, 1)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "folder" in scrape_item.url.parts:
            return await self.folder(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        folder_key = scrape_item.url.parts[2]
        try:
            folder_details: dict[str, dict] = self.api.folder_get_info(folder_key=folder_key)  # type: ignore
        except api.MediaFireApiError as e:
            raise MediaFireError(status=e.code, message=e.message) from None

        title = self.create_title(folder_details["folder_info"]["name"], folder_key)
        scrape_item.setup_as_album(title)

        for chunk in itertools.count(1):
            try:
                folder_contents: dict[str, Any] = self.api.folder_get_content(
                    folder_key, "files", chunk=chunk, chunk_size=100
                )  # type: ignore
            except api.MediaFireApiError as e:
                raise MediaFireError(status=e.code, message=e.message) from None

            for file in folder_contents["folder_content"]["files"]:
                date = self.parse_date(file["created"])
                link = self.parse_url(file["links"]["normal_download"])
                new_scrape_item = scrape_item.create_child(link, new_title_part=title, possible_datetime=date)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            if not folder_contents["folder_content"]["more_chunks"] == "yes":
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_tag = soup.select_one(DOWNLOAD_BUTTON_SELECTOR)
        if not link_tag:
            if "Something appears to be missing" in soup.get_text():
                raise ScrapeError(410)
            raise ScrapeError(422)

        scrape_item.possible_datetime = self.parse_iso_date(soup.select(DATE_SELECTOR)[-1].get_text())
        link_str: str = css.get_attr(link_tag, "href")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
