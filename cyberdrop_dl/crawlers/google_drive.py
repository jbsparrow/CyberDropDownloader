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
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import DownloadError, ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_from_headers

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


VALID_FILE_URL_PARTS = "file", "document", "presentation", "spreadsheets"
ITEM_SELECTOR = "div.flip-entry-info > a"


@dataclass(frozen=True, slots=True)
class GoogleDriveFolder:
    id: str
    title: str
    items: tuple[str]


class GoogleDriveCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"drive.google": ["drive.google", "docs.google"]}
    primary_base_domain = URL("https://drive.google.com")

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "GoogleDrive")
        self.request_limiter = AsyncLimiter(4, 6)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
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
            link: URL = self.parse_url(link_str)
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
            soup: BeautifulSoup = await self.client.get_soup(self.domain, download_url)

        title: str = soup.title.text.strip()  # type: ignore
        children = []
        for item in soup.select(ITEM_SELECTOR):
            link = item.get("href")
            if not link:
                continue
            children.append(link)
        children = tuple(children)
        return GoogleDriveFolder(folder_id, title, children)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str = "") -> None:  # type: ignore
        file_id = file_id or get_file_id(scrape_item.url)
        if not file_id:
            raise ScrapeError(422)

        canonical_url = get_canonical_url(file_id)
        if await self.check_complete_from_referer(canonical_url):
            return

        download_url = get_download_url(file_id)
        link, headers = await self.get_file_url_and_headers(download_url, file_id)
        scrape_item.url = canonical_url

        filename = get_filename_from_headers(headers) or link.name
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)

    async def get_file_url_and_headers(self, url: URL, file_id: str) -> tuple[URL, Mapping[str, str]]:
        soup = last_error = None
        current_url: URL | None = url
        try_file_open_url = True

        headers = {}
        while current_url:
            current_url, headers = await self.add_headers(current_url)
            if are_valid_headers(headers):
                return current_url, headers

            try:
                async with self.request_limiter:
                    response, soup = await self.client._get_response_and_soup(self.domain, current_url)
                    headers = response.headers

            except DownloadError as e:
                last_error = e
                if e.status == 500 and try_file_open_url:
                    current_url = URL(f"https://drive.google.com/open?id={file_id}")
                    try_file_open_url = False
                    continue

            if not soup:
                raise last_error or ScrapeError(400)

            if docs_url := get_docs_url(soup, file_id):
                current_url = docs_url
                continue

            if are_valid_headers(headers):
                return current_url, headers

            current_url = self.get_url_from_download_button(soup)
            if not current_url:
                break
            return await self.add_headers(current_url)

        raise ScrapeError(422)

    async def add_headers(self, url: URL) -> tuple[URL, Mapping[str, str]]:
        async with self.request_limiter:
            headers = await self.client.get_head(self.domain, url)
        location = headers.get("location")
        if location:
            link = self.parse_url(location)
            return await self.add_headers(link)
        return url, headers

    def get_url_from_download_button(self, soup: BeautifulSoup) -> URL | None:
        form = soup.select_one("#download-form")
        if not form:
            return None

        url_str: str = form["action"]  # type: ignore
        url: URL = self.parse_url(url_str.replace("&amp;", "&"))
        query_params = dict(url.query)

        input_tags = soup.select('input[type="hidden"]')
        for input_tag in input_tags:
            query_params[input_tag.get("name")] = input_tag.get("value")  # type: ignore

        return url.with_query(query_params)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def get_docs_url(soup: BeautifulSoup, file_id: str) -> URL | None:
    title: str = soup.title.text  # type: ignore
    if title.endswith(" - Google Docs"):
        return URL(f"https://docs.google.com/document/d/{file_id}/export?format=docx")
    if title.endswith(" - Google Sheets"):
        return URL(f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx")
    if title.endswith(" - Google Slides"):
        return URL(f"https://docs.google.com/presentation/d/{file_id}/export?format=pptx")


def get_id_from_query(url: URL) -> str | None:
    item_id = url.query.get("id")
    if item_id:
        if len(item_id) == 1:
            return item_id[1]
        return item_id


def get_file_id(url: URL) -> str:
    file_id = get_id_from_query(url)
    if file_id:
        return file_id

    if "d" in url.parts and any(p in url.parts for p in VALID_FILE_URL_PARTS):
        file_id_index = url.parts.index("d") + 1
        if len(url.parts) > file_id_index:
            return url.parts[file_id_index]
    return ""


def get_folder_id(url: URL) -> str:
    # URL should have been pre-validated with `is_folder`
    folder_id = get_id_from_query(url)
    if folder_id:
        return folder_id

    folder_id_index = url.parts.index("folders") + 1
    if len(url.parts) > folder_id_index:
        return url.parts[folder_id_index]
    return ""


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def get_canonical_url(item_id: str, folder: bool = False) -> URL:
    if folder:
        return URL(f"https://drive.google.com/drive/folders/{item_id}")
    return URL(f"https://drive.google.com/file/d/{item_id}")


def get_download_url(item_id: str, folder: bool = False) -> URL:
    if folder:
        return URL(f"https://drive.google.com/embeddedfolderview?id={item_id}")
    return URL(f"https://drive.google.com/uc?export=download&id={item_id}")


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def are_valid_headers(headers: Mapping[str, str]):
    return "Content-Disposition" in headers and not is_html(headers)


def is_html(headers: Mapping[str, str]) -> bool:
    content_type: str = headers.get("Content-Type", "").lower()
    return any(s in content_type for s in ("html", "text"))


def is_folder(url: URL) -> bool:
    return "/drive/folders/" in url.path or "embeddedfolderview" in url.parts


def is_download_page(url: URL) -> bool:
    return url.name == "uc" or "usercontent" in url.host  # type: ignore
