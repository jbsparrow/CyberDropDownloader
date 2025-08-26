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
_DOC_FORMATS = {"spreadsheets": "xlsx", "presentation": "pptx", "document": "docx"}


class GoogleDriveCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Docs": "/document/d/<file_id>",
        "Files": ("/d/<file_id>", "/file/d/<file_id>"),
        "Folders": "/drive/folders/<folder_id>",
        "Sheets": "/spreadsheets/d/<file_id>",
        "Slides": "/presentation/d/<file_id>",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "drive.google", "docs.google", "drive.usercontent.google.com"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "drive.google"
    FOLDER_DOMAIN: ClassVar[str] = "GoogleDrive"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(4, 6)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        url = scrape_item.url
        if file_id := url.query.get("id"):
            return await self.file(scrape_item, file_id)

        def next_to(name: str):
            try:
                index = url.parts.index(name)
                return url.parts[index + 1]
            except (ValueError, IndexError):
                return

        if folder_id := (next_to("folders") or next_to("embeddedfolderview")):
            return await self.folder(scrape_item, folder_id)

        if file_id := next_to("d"):
            format = url.query.get("format") or next((f for x, f in _DOC_FORMATS.items() if x in url.parts), None)
            return await self.file(scrape_item, file_id, format)

        raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_id: str) -> None:
        embeded_folder_url = (self.PRIMARY_URL / "embeddedfolderview").with_query(id=folder_id)
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, embeded_folder_url)

        folder_name = css.select_one_get_text(soup, "title")
        title = self.create_title(folder_name, folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)

        for index, (_, child) in enumerate(self.iter_tags(soup, _FOLDER_ITEM_SELECTOR), 1):
            new_scrape_item = scrape_item.create_child(child)
            self.create_task(self.run(new_scrape_item))
            scrape_item.add_children()
            if index % 200 == 0:
                await asyncio.sleep(0)

    async def file(self, scrape_item: ScrapeItem, file_id: str = "", format: str | None = None) -> None:
        # from personal testing, file ids are always 33 chars, doc ids are always 44 chars
        # but i did not find any official docs about it
        if len(file_id) < 25:
            raise ValueError

        looks_like_google_docs = len(file_id) > 40
        if looks_like_google_docs and not format:
            msg = f"[{self.FOLDER_DOMAIN}] {file_id=} looks like a google docs file but no format was specified. Falling back to pdf"
            self.log(msg, 30)
            format = "pdf"

        format = format if looks_like_google_docs else None
        return await self._file(scrape_item, file_id, format)

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, file_id: str, format: str | None) -> None:
        canonical_url = self.PRIMARY_URL / "file/d" / file_id
        if format:
            canonical_url = canonical_url.with_query(format=format)

        scrape_item.url = canonical_url
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
