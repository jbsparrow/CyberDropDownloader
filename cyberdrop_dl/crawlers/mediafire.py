from __future__ import annotations

import base64
import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from mediafire import MediaFireApi, api

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import MediaFireError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, is_blob_or_svg

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

DOWNLOAD_BUTTON_SELECTOR = "a[id=downloadButton]"
DATE_SELECTOR = "ul[class=details] li span"
PRIMARY_URL = AbsoluteHttpURL("https://www.mediafire.com/")
API_URL = PRIMARY_URL / "api/1.4"


class MediaFireCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "File": "/file/...",
        "Folder": "/folder/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "mediafire"
    _RATE_LIMIT = 5, 1

    def __post_init__(self) -> None:
        self.api = MediaFireApi()

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

        soup = await self.request_soup(scrape_item.url, impersonate=True)
        scrape_item.possible_datetime = self.parse_iso_date(soup.select(DATE_SELECTOR)[-1].get_text())
        link = self.parse_url(_extract_download_link(soup))
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)


def _extract_download_link(soup: BeautifulSoup) -> str:
    link_tag = soup.select_one(DOWNLOAD_BUTTON_SELECTOR)
    if not link_tag:
        if "Something appears to be missing" in soup.get_text():
            raise ScrapeError(410)
        raise ScrapeError(422)

    if encoded_url := css.get_attr_or_none(link_tag, "data-scrambled-url"):
        return base64.urlsafe_b64decode(encoded_url).decode()

    url = css.get_attr(link_tag, "data-scrambled-url")
    if is_blob_or_svg(url):
        raise ScrapeError(422)
    return url
