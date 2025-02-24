from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


BLOCK_FOLDER_DOWNLOADS = False


class DropboxCrawler(Crawler):
    primary_base_domain = URL("https://dropbox.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "dropbox", "Dropbox")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        scrape_item.url = await self.get_share_url(scrape_item)
        if not scrape_item.url:
            return

        if any(p in scrape_item.url.path for p in ("/scl/fi/", "/scl/fo/")):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a dropbox file"""
        item = get_item_info(scrape_item.url)
        if not item.is_file and BLOCK_FOLDER_DOWNLOADS:
            raise ScrapeError(422)

        if await self.check_complete_from_referer(item.view_url):
            return

        if not item.rlkey:
            raise ScrapeError(401)

        scrape_item.url = item.view_url
        filename = item.filename or await self.get_folder_name(item.download_url)
        if not filename:
            raise ScrapeError(422)
        filename, ext = get_filename_and_ext(filename)
        await self.handle_file(item.canonical_url, scrape_item, filename, ext, debrid_link=item.download_url)

    @error_handling_wrapper
    async def get_share_url(self, scrape_item: ScrapeItem) -> URL:
        if not any(p in scrape_item.url.parts for p in ("s", "sh")):
            return scrape_item.url
        return await self.get_redict_url(scrape_item.url)

    async def get_folder_name(self, url: URL) -> str | None:
        url = await self.get_redict_url(url)
        async with self.request_limiter:
            headers: dict = await self.client.get_head(self.domain, url)
        if not are_valid_headers(headers):
            raise ScrapeError(422)
        return get_filename_from_headers(headers)

    async def get_redict_url(self, url: URL) -> URL:
        async with self.request_limiter:
            headers: dict = await self.client.get_head(self.domain, url)
        location = headers.get("location")
        if not location:
            raise ScrapeError(400)
        return self.parse_url(location)


@dataclass
class DropboxItem:
    file_id: str | None
    folder_tokens: tuple[str, str] | None
    url: URL
    rlkey: str
    filename: str

    @property
    def is_file(self) -> bool:
        return bool(self.filename)

    @cached_property
    def canonical_url(self) -> URL:
        if not self.is_file:
            return URL(self._folder_url_str)
        if not self.file_id:
            return URL(f"{self._folder_url_str}?preview={self.filename}")
        return URL(f"https://www.dropbox.com/scl/fi/{self.file_id}")

    @cached_property
    def download_url(self) -> URL:
        return self.canonical_url.update_query(dl=1, rlkey=self.rlkey)

    @cached_property
    def view_url(self) -> URL:
        return self.canonical_url.with_query(rlkey=self.rlkey, e=1, dl=0)

    @cached_property
    def _folder_url_str(self) -> str:
        if not self.folder_tokens:
            return ""
        path = "/".join(self.folder_tokens)
        return f"https://www.dropbox.com/scl/fo/{path}"


def get_item_info(url: URL) -> DropboxItem:
    """Parses item information from the url.

    See https://www.dropboxforum.com/discussions/101001012/shared-link--scl-to-s/689070

    """
    filename = url.query.get("preview") or ""
    if not filename and "/scl/fi/" in url.path:
        filename_index = url.parts.index("fi") + 2
        filename = url.parts[filename_index]

    from_folder = "/scl/fo/" in url.path
    rlkey = url.query.get("rlkey") or ""
    folder_tokens = file_id = None
    if from_folder:
        folder_id_index = url.parts.index("fo") + 1
        folder_tokens = url.parts[folder_id_index], url.parts[folder_id_index + 1]
    else:
        file_id_index = url.parts.index("fi") + 1
        file_id = url.parts[file_id_index]

    return DropboxItem(file_id, folder_tokens, url, rlkey, filename)


FILENAME_REGEX_STR = r"filename\*=UTF-8''(.+)|.*filename=\"(.*?)\""
FILENAME_REGEX = re.compile(FILENAME_REGEX_STR, re.IGNORECASE)


def get_filename_from_headers(headers: dict) -> str | None:
    content_disposition = headers.get("Content-Disposition")
    if not content_disposition:
        return
    match = re.search(FILENAME_REGEX, content_disposition)
    if match:
        matches = match.groups()
        return matches[0] or matches[1]


def are_valid_headers(headers: dict):
    return "Content-Disposition" in headers and not is_html(headers)


def is_html(headers: dict) -> bool:
    content_type: str = headers.get("Content-Type", "").lower()
    return any(s in content_type for s in ("html", "text"))
