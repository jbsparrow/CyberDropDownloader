from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedPaths
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_from_headers

if TYPE_CHECKING:
    from collections.abc import Mapping

    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class DropboxCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Files": "/scl/fi/...",
        "Folders": "/scl/fo/...",
        "**NOTE**": "Folders will be downloaded as a zip file.",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://dropbox.com/")
    DOMAIN: ClassVar[str] = "dropbox"

    def __post_init__(self) -> None:
        self.download_folders = self.manager.parsed_args.cli_only_args.download_dropbox_folders_as_zip

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        url = await self.get_share_url(scrape_item)
        if not url:
            return
        scrape_item.url = url

        if any(p in scrape_item.url.path for p in ("/scl/fi/", "/scl/fo/")):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        item = get_item_info(scrape_item.url)
        if not item.is_file and not self.download_folders:
            raise ScrapeError(422, message="Folders download is not enabled")

        if await self.check_complete_from_referer(item.view_url):
            return

        if not item.rlkey:
            raise ScrapeError(401)

        scrape_item.url = item.view_url
        filename = item.filename or await self.get_folder_name(item.download_url)
        if not filename:
            raise ScrapeError(422)
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(item.canonical_url, scrape_item, filename, ext, debrid_link=item.download_url)

    @error_handling_wrapper
    async def get_share_url(self, scrape_item: ScrapeItem) -> AbsoluteHttpURL:
        if not any(p in scrape_item.url.parts for p in ("s", "sh")):
            return scrape_item.url
        return await self.get_redict_url(scrape_item.url)

    async def get_folder_name(self, url: URL) -> str | None:
        url = await self.get_redict_url(url)
        async with self.request_limiter:
            headers = await self.client.get_head(self.DOMAIN, url)
        if not ("Content-Disposition" in headers and not is_html(headers)):
            raise ScrapeError(422)
        return get_filename_from_headers(headers)

    async def get_redict_url(self, url: URL) -> AbsoluteHttpURL:
        async with self.request_limiter:
            headers = await self.client.get_head(self.DOMAIN, url)
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
    def canonical_url(self) -> AbsoluteHttpURL:
        if not self.is_file:
            return AbsoluteHttpURL(self._folder_url_str)
        if not self.file_id:
            return AbsoluteHttpURL(f"{self._folder_url_str}?preview={self.filename}")
        return AbsoluteHttpURL(f"https://www.dropbox.com/scl/fi/{self.file_id}")

    @cached_property
    def download_url(self) -> URL:
        return self.canonical_url.update_query(dl=1, rlkey=self.rlkey)

    @cached_property
    def view_url(self) -> AbsoluteHttpURL:
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


def is_html(headers: Mapping[str, str]) -> bool:
    content_type: str = headers.get("Content-Type", "").lower()
    return any(s in content_type for s in ("html", "text"))
