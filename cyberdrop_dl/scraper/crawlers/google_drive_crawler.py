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

import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import DownloadError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


FILENAME_REGEX_STR = r"filename\*=UTF-8''(.+)|.*filename=\"(.*?)\""
FILENAME_REGEX = re.compile(FILENAME_REGEX_STR, re.IGNORECASE)

VALID_FILE_URL_PARTS = "file", "document", "presentation", "spreadsheets"


class GoogleDriveCrawler(Crawler):
    primary_base_domain = URL("https://drive.google.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "drive.google", "gDrive")
        self.request_limiter = AsyncLimiter(1, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        await self.file(scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        file_id = get_file_id(scrape_item.url)
        if not file_id:
            raise ValueError

        canonical_url = get_canonical_url(file_id)
        if await self.check_complete_from_referer(canonical_url):
            return

        link, headers = await self.get_file_url_and_headers(scrape_item.url, file_id)
        scrape_item.url = canonical_url

        filename = get_filename_from_headers(headers) or link.name
        scrape_item.possible_datetime = get_datetime_from_headers(headers)
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)

    async def get_file_url_and_headers(self, url: URL, file_id: str) -> tuple[URL, dict]:
        soup: BeautifulSoup | None = None
        current_url: URL | None = url
        try_file_open_url = True
        last_error = None
        headers = {}
        while current_url:
            current_url, headers = await self.add_headers(current_url)
            if are_valid_headers(headers):
                return current_url, headers

            try:
                async with self.request_limiter:
                    soup, headers = await self.client.get_soup(self.domain, current_url, with_response_headers=True)
            except DownloadError as e:
                last_error = e
                if e.status == 500 and try_file_open_url:
                    current_url = URL(f"https://drive.google.com/open?id={file_id}")
                    try_file_open_url = False
                    continue

            docs_url = get_docs_url(soup, file_id)
            if docs_url:
                current_url = docs_url
                continue

            if are_valid_headers(headers):
                return current_url, headers

            if not soup and last_error:
                raise last_error

            current_url = get_url_from_download_button(soup, self.parse_url)
            if not current_url:
                break
            return await self.add_headers(current_url)

            # "googleusercontent" in current_url.host
        raise ScrapeError(422)

    async def add_headers(self, url: URL) -> tuple[URL, dict]:
        async with self.request_limiter:
            headers: dict = await self.client.get_head(self.domain, url)
        location = headers.get("location")
        if location:
            link = self.parse_url(location)
            return await self.add_headers(link)
        return url, headers


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def are_valid_headers(headers: dict):
    return "Content-Disposition" in headers and not is_text(headers)


def is_text(headers: dict) -> bool:
    content_type: str = headers.get("Content-Type", "")
    return any(s in content_type.lower() for s in ("html", "text"))


def get_docs_url(soup: BeautifulSoup, file_id: str) -> URL | None:
    title: str = soup.title.text
    if title.endswith(" - Google Docs"):
        return URL(f"https://docs.google.com/document/d/{file_id}/export?format=docx")
    if title.endswith(" - Google Sheets"):
        return URL(f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx")
    if title.endswith(" - Google Slides"):
        return URL(f"https://docs.google.com/presentation/d/{file_id}/export?format=pptx")


def get_file_details(url: URL) -> tuple[str | None, bool]:
    is_direct = is_download_page(url)
    file_id = get_file_id(url)
    return file_id, is_direct


def get_file_id(url: URL) -> str | None:
    file_id = url.query.get("id")
    if file_id:
        if len(file_id) == 1:
            return file_id[1]
        return file_id

    if "d" in url.parts and any(p in url.parts for p in VALID_FILE_URL_PARTS):
        file_id_index = url.parts.index("d") + 1
        return url.parts[file_id_index]


def get_filename_from_headers(headers: dict) -> str | None:
    content_disposition = headers.get("Content-Disposition")
    if not content_disposition:
        return ""
    match = re.search(FILENAME_REGEX, content_disposition)
    if match:
        matches = match.groups()
        return matches[0] or matches[1]


def get_datetime_from_headers(headers: dict) -> int | None:
    date = headers.get("Last-Modified")
    if date:
        return date


def get_canonical_url(id_: str, folder: bool = False) -> URL:
    if folder:
        return URL(f"https://drive.google.com/drive/folders/{id_}")
    return URL(f"https://drive.google.com/file/d/{id_}")


def get_url_from_download_button(soup: BeautifulSoup, url_parser: Callable[..., URL]) -> URL | None:
    ### Todo handle docs,slides and spread sheets
    form = soup.select_one("#download-form")
    if not form:
        return None

    url_str: str = form["action"]  # type: ignore
    url: URL = url_parser(url_str.replace("&amp;", "&"))
    query_params = dict(url.query)

    input_tags = soup.select('input[type="hidden"]')
    for input_tag in input_tags:
        query_params[input_tag.get("name")] = input_tag.get("value")  # type: ignore

    return url.with_query(query_params)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def is_folder(url: URL) -> bool:
    return "/drive/folders/" in url.path


def is_download_page(url: URL) -> bool:
    return url.name == "uc" or "usercontent" in url.host
