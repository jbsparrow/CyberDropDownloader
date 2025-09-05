# SPDX-License-Identifier: GPL-3.0
#
# Licensed under GPL-3.0 as detailed in the root LICENSE file
#
# The code in this file has been adapted from an MIT-licensed source.
# See the MIT License section below for details.
#
# Original code from https://github.com/wkentaro/gdown by Kentaro Wada (wkentaro)
#
# ----------------------------------------------------------------------
# MIT License
# ----------------------------------------------------------------------
#
# Copyright (c) 2015 Kentaro Wada
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


# This versions numbers and restrictions are not documented and may actually be wrong
# These values are just from personal experience
_KNOWN_FILE_ID_VERSIONS = 0, 1
_DRIVE_ID_LEN = 28  # v0 uses 28, v1 uses 33
_DOCS_ID_LEN = 44  # v1 uses 44. I have not seen v0 doc URL


_PRIMARY_URL = AbsoluteHttpURL("https://drive.google.com")
_DOCS_URL = AbsoluteHttpURL("https://docs.google.com")

_FOLDER_ITEM_SELECTOR = "div.flip-entry-info > a[href]"
_DOC_FORMATS: dict[str, tuple[str, ...]] = {
    "spreadsheets": ("xslx", "ods", "html", "csv", "tsv"),
    "presentation": ("pptx", "odp"),
    "document": ("docx", "odt", "rtf", "txt", "epub", "pdf", "md", "zip"),
}


def _valid_formats_string() -> str:
    string = ""
    sep = "\n  - "
    for doc, formats in sorted(_DOC_FORMATS.items()):
        default, *others = formats
        string += f"\n\n{doc}:{sep}"
        string += sep.join(sorted((f"{default} (default)", *others)))
    return string


class GoogleDriveCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Files": "/file/d/<file_id>",
        "Folders": (
            "/drive/folders/<folder_id>",
            "/embeddedfolderview/<folder_id>",
        ),
        "Docs": "/document/d/<file_id>",
        "Sheets": "/spreadsheets/d/<file_id>",
        "Slides": "/presentation/d/<file_id>",
        "**NOTE**": (
            "You can download sheets, slides and docs in a custom format by using it as a query param.\n"
            "ex: https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=ods\n"
            f"Valid Formats:{_valid_formats_string()}"
        ),
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "drive.google", "docs.google", "drive.usercontent.google.com"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "drive.google"
    FOLDER_DOMAIN: ClassVar[str] = "GoogleDrive"

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
            if (first := url.parts[1]) in _DOC_FORMATS:
                doc = first
            else:
                doc = None
            return await self.file(scrape_item, file_id, doc)

        raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem, folder_id: str) -> None:
        embeded_folder_url = (self.PRIMARY_URL / "embeddedfolderview").with_query(id=folder_id)
        soup = await self.request_soup(embeded_folder_url)

        folder_name = css.select_one_get_text(soup, "title")
        title = self.create_title(folder_name, folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)

        for index, (_, child) in enumerate(self.iter_tags(soup, _FOLDER_ITEM_SELECTOR), 1):
            new_scrape_item = scrape_item.create_child(child)
            self.create_task(self.run(new_scrape_item))
            scrape_item.add_children()
            if index % 200 == 0:
                await asyncio.sleep(0)

    async def file(self, scrape_item: ScrapeItem, file_id: str = "", doc: str | None = None) -> None:
        version = int(file_id[0])
        if version not in _KNOWN_FILE_ID_VERSIONS:
            msg = f"{scrape_item.url} has an unknown file_id {version = }. Falling back to download as normal file"
            self.log(msg, 30)
            return await self._drive_file(scrape_item, file_id)

        if len(file_id) < _DRIVE_ID_LEN:
            msg = f"{scrape_item.url} has an invalid file_id. Needs to be at least {_DRIVE_ID_LEN} long"
            self.log(msg, 40)
            raise ValueError

        if len(file_id) < _DOCS_ID_LEN:
            return await self._drive_file(scrape_item, file_id)

        return await self._docs_file(scrape_item, file_id, doc)

    async def _drive_file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        scrape_item.url = _PRIMARY_URL / "file/d" / file_id
        export_url = (_PRIMARY_URL / "uc").with_query(id=file_id, export="download", confirm="True")
        return await self._file(scrape_item, export_url)

    @error_handling_wrapper
    async def _docs_file(self, scrape_item: ScrapeItem, file_id: str, doc: str | None) -> None:
        if not doc:
            open_url = (_DOCS_URL / "open").with_query(id=file_id)
            url = await self._get_redirect_url(open_url)
            if (first := url.parts[1]) in _DOC_FORMATS:
                doc = first

        if not doc:
            raise ScrapeError(422, "Unable to identify google docs file type")

        format_ = scrape_item.url.query.get("format")
        proper_format = _get_proper_doc_format(doc, format_)
        if format_ and format_ != proper_format:
            msg = f"{scrape_item.url} with {format_ = } is not valid. Falling back to {proper_format}"
            self.log(msg, 30)

        scrape_item.url = (_DOCS_URL / doc / "d" / file_id).with_query(format=proper_format)
        export_url = (_DOCS_URL / doc / "export").with_query(id=file_id, format=proper_format)
        return await self._file(scrape_item, export_url)

    @error_handling_wrapper
    async def _file(self, scrape_item: ScrapeItem, export_url: AbsoluteHttpURL) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        link, name = await self._get_file_info(export_url)
        filename, ext = self.get_filename_and_ext(name)
        await self.handle_file(scrape_item.url, scrape_item, name, ext, debrid_link=link, custom_filename=filename)

    async def _get_file_info(self, export_url: AbsoluteHttpURL) -> tuple[AbsoluteHttpURL, str]:
        # Use POST request to bypass "file is too large to scan. Would you still like to download this file" warning
        method = "GET" if export_url.host == _DOCS_URL.host else "POST"

        async with self.request(export_url, method=method) as resp:
            assert resp.ok and "html" not in resp.content_type

        return resp.url, resp.filename


def _get_proper_doc_format(doc: str, format: str | None) -> str:
    valid_formats = _DOC_FORMATS[doc]
    if format in valid_formats:
        return format

    return valid_formats[0]
