from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar, cast

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://drive.google.com")
_DOCS_DOWNLOAD = AbsoluteHttpURL("https://docs.google.com/document/export")
_FILE_DOWNLOAD = _PRIMARY_URL / "uc"
_FOLDER_ITEM_SELECTOR = "div.flip-entry-info > a[href]"
_DOC_FORMATS = {
    "file": None,
    "spreadsheets": "xlsx",
    "presentation": "pptx",
    "document": "docx",
}


class GoogleDriveCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Docs": "/document/d/<file_id>",
        "Files": ("/d/<file_id>", "/file/d/<file_id>"),
        "Folders": "/drive/folders/<folder_id>",
        "Sheets": "/spreadsheets/d/<file_id>",
        "Slides": "/presentation/d/<file_id>",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "drive.google", "docs.google", "drive.usercontent.google.com"
    PRIMARY_URL = _PRIMARY_URL
    DOMAIN = "drive.google"
    FOLDER_DOMAIN = "GoogleDrive"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "drive.google"
    FOLDER_DOMAIN: ClassVar[str] = "GoogleDrive"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(4, 6)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        url = scrape_item.url
        is_user_content = "usercontent" in url.host or url.path == "/uc"
        if is_user_content and (file_id := url.query.get("id")):
            return await self.file(scrape_item, file_id)

        match scrape_item.url.parts[1:]:
            case ["drive", "folders", folder_id, *_]:
                return await self.folder(scrape_item, folder_id)
            case ["embeddedfolderview", folder_id, *_]:
                return await self.folder(scrape_item, folder_id)
            case ["d", file_id, *_]:
                return await self.file(scrape_item, file_id)
            case [doc, "d", file_id, *_] if doc in _DOC_FORMATS:
                format = url.query.get("format") or _DOC_FORMATS[doc]
                return await self.file(scrape_item, file_id, format)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_id: str) -> None:
        embeded_folder_url = (self.PRIMARY_URL / "embeddedfolderview").with_query(id=folder_id)
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, embeded_folder_url)

        folder_name = css.select_one_get_text(soup, "title")
        title = self.create_title(folder_name, folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)
        results = await self.get_album_results(folder_id)

        for index, (_, child) in enumerate(self.iter_tags(soup, _FOLDER_ITEM_SELECTOR), 1):
            if self.check_album_results(child, results):
                continue

            new_scrape_item = scrape_item.create_child(child)
            self.create_task(self.run(new_scrape_item))
            scrape_item.add_children()
            if index % 200 == 0:
                await asyncio.sleep(0)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str = "", format: str | None = None) -> None:
        scrape_item.url = canonical_url = self.PRIMARY_URL / "file/d" / file_id
        if await self.check_complete_from_referer(canonical_url):
            return

        link, filename = await self._get_file_info(file_id, format)
        custom_filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, debrid_link=link, custom_filename=custom_filename
        )

    async def _get_file_info(self, file_id: str, format: str | None) -> tuple[AbsoluteHttpURL, str]:
        if format:
            method, url = "GET", _DOCS_DOWNLOAD.with_query(id=file_id, format=format)
        else:
            method, url = "POST", _FILE_DOWNLOAD.with_query(id=file_id, export="download", confirm="True")

        # TODO: This request bypasses the config limiter. Use the new request method when PR #1251 is merged
        async with self.request_limiter, self.client._session.request(method, url) as resp:
            if not resp.ok or "html" in resp.content_type:
                await self.client.client_manager.check_http_status(resp)

        direct_url = cast("AbsoluteHttpURL", resp.url)
        filename: str = resp.content_disposition.filename  # type: ignore[reportAssignmentType,reportOptionalMemberAccess]
        return direct_url, filename
