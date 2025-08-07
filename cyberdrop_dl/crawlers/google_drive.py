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

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DownloadError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


VALID_FILE_URL_PARTS = "file", "document", "presentation", "spreadsheets"
ITEM_SELECTOR = "div.flip-entry-info > a"


@dataclass(frozen=True, slots=True)
class GoogleDriveFolder:
    id: str
    title: str
    items: tuple[str]


PRIMARY_URL = AbsoluteHttpURL("https://drive.google.com")


class GoogleDriveCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Docs": "/document/d/<file_id>",
        "Files": "/d/<file_id>",
        "Folders": "/drive/folders/<folder_id>",
        "Sheets": "/spreadsheets/d/<file_id>",
        "Slides": "/presentation/d/<file_id>",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "drive.google", "docs.google"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "drive.google"
    FOLDER_DOMAIN: ClassVar[str] = "GoogleDrive"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(4, 6)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if is_folder(scrape_item.url):
            return await self.folder(scrape_item)

        if file_id := get_file_id(scrape_item.url):
            return await self.file(scrape_item, file_id)

        raise ValueError

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        folder = await self.get_folder_details(scrape_item)
        title = self.create_title(folder.title, folder.id)
        scrape_item.setup_as_album(title, album_id=folder.id)
        results = await self.get_album_results(folder.id)

        subfolders = []
        for link_str in folder.items:
            link = self.parse_url(link_str)
            if is_folder(link):
                subfolders.append(link)
                continue
            if not self.check_album_results(link, results):
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

        for folder_link in subfolders:
            new_scrape_item = scrape_item.create_child(folder_link)
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    async def get_folder_details(self, scrape_item: ScrapeItem) -> GoogleDriveFolder:
        folder_id = get_folder_id(scrape_item.url)
        download_url = get_download_url(folder_id, folder=True)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, download_url)

        title: str = css.select_one_get_text(soup, "title")
        children = []
        for item in soup.select(ITEM_SELECTOR):
            link = item.get("href")
            if not link:
                continue
            children.append(link)
        children = tuple(children)
        return GoogleDriveFolder(folder_id, title, children)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str = "") -> None:
        file_id = file_id or get_file_id(scrape_item.url)
        if not file_id:
            raise ScrapeError(422)

        canonical_url = get_canonical_url(file_id)
        if await self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        download_url = get_download_url(file_id)
        link, filename = await self.get_file_url_and_name(download_url, file_id)
        filename, ext = self.get_filename_and_ext(filename or link.name)
        await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)

    async def get_file_url_and_name(self, url: AbsoluteHttpURL, file_id: str) -> tuple[AbsoluteHttpURL, str | None]:
        soup = last_error = response = None
        current_url: AbsoluteHttpURL | None = url
        try_file_open_url = True

        while current_url:
            current_url, filename = await self.add_filename(current_url)
            if filename:
                return current_url, filename

            try:
                async with self.request_limiter:
                    response, soup = await self.client._get_response_and_soup(self.DOMAIN, current_url)

            except DownloadError as e:
                last_error = e
                if e.status == 500 and try_file_open_url:
                    current_url = AbsoluteHttpURL(f"https://drive.google.com/open?id={file_id}")
                    try_file_open_url = False
                    continue

            if not soup:
                raise last_error or ScrapeError(400)

            if docs_url := get_docs_url(soup, file_id):
                current_url = docs_url
                continue

            if response and response.content_disposition and response.content_disposition.filename:
                return current_url, response.content_disposition.filename

            current_url = self.get_url_from_download_button(soup)
            if not current_url:
                break

            return await self.add_filename(current_url)

        raise ScrapeError(422)

    async def add_filename(self, url: AbsoluteHttpURL) -> tuple[AbsoluteHttpURL, str | None]:
        async with self.request_limiter:
            response = await self.client._get_head(self.DOMAIN, url)
        location = response.headers.get("location")
        if location:
            link = self.parse_url(location)
            return await self.add_filename(link)
        if response.content_disposition and response.content_disposition.filename:
            return url, response.content_disposition.filename
        return url, None

    def get_url_from_download_button(self, soup: BeautifulSoup) -> AbsoluteHttpURL | None:
        form = soup.select_one("#download-form")
        if not form:
            return None

        url_str: str = css.get_attr(form, "action")
        url: AbsoluteHttpURL = self.parse_url(url_str.replace("&amp;", "&"))
        query_params = dict(url.query)

        input_tags = soup.select('input[type="hidden"]')
        for input_tag in input_tags:
            query_params[css.get_attr(input_tag, "name")] = css.get_attr(input_tag, "value")

        return url.with_query(query_params)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def get_docs_url(soup: BeautifulSoup, file_id: str) -> AbsoluteHttpURL | None:
    title: str = css.select_one_get_text(soup, "title")
    if title.endswith(" - Google Docs"):
        return AbsoluteHttpURL(f"https://docs.google.com/document/d/{file_id}/export?format=docx")
    if title.endswith(" - Google Sheets"):
        return AbsoluteHttpURL(f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx")
    if title.endswith(" - Google Slides"):
        return AbsoluteHttpURL(f"https://docs.google.com/presentation/d/{file_id}/export?format=pptx")


def get_id_from_query(url: AbsoluteHttpURL) -> str | None:
    if item_id := url.query.get("id"):
        if len(item_id) == 1:
            return item_id[1]
        return item_id


def get_file_id(url: AbsoluteHttpURL) -> str:
    if file_id := get_id_from_query(url):
        return file_id

    if "d" in url.parts and any(p in url.parts for p in VALID_FILE_URL_PARTS):
        file_id_index = url.parts.index("d") + 1
        if len(url.parts) > file_id_index:
            return url.parts[file_id_index]
    return ""


def get_folder_id(url: AbsoluteHttpURL) -> str:
    # URL should have been pre-validated with `is_folder`
    folder_id = get_id_from_query(url)
    if folder_id:
        return folder_id

    folder_id_index = url.parts.index("folders") + 1
    if len(url.parts) > folder_id_index:
        return url.parts[folder_id_index]
    return ""


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def get_canonical_url(item_id: str, folder: bool = False) -> AbsoluteHttpURL:
    if folder:
        return AbsoluteHttpURL(f"https://drive.google.com/drive/folders/{item_id}")
    return AbsoluteHttpURL(f"https://drive.google.com/file/d/{item_id}")


def get_download_url(item_id: str, folder: bool = False) -> AbsoluteHttpURL:
    if folder:
        return AbsoluteHttpURL(f"https://drive.google.com/embeddedfolderview?id={item_id}")
    return AbsoluteHttpURL(f"https://drive.google.com/uc?export=download&id={item_id}")


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def are_valid_headers(headers: Mapping[str, str]):
    return "Content-Disposition" in headers and not is_html(headers)


def is_html(headers: Mapping[str, str]) -> bool:
    content_type: str = headers.get("Content-Type", "").lower()
    return any(s in content_type for s in ("html", "text"))


def is_folder(url: AbsoluteHttpURL) -> bool:
    return "/drive/folders/" in url.path or "embeddedfolderview" in url.parts


def is_download_page(url: AbsoluteHttpURL) -> bool:
    return url.name == "uc" or "usercontent" in url.host
