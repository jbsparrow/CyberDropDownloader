"""Real-Debrid API Implementation. All methods return their JSON response (if any).

For details, visit: https://api.real-debrid.com

All API methods require authentication except the regexes

The API is limited to 250 requests per minute.
"""

from __future__ import annotations

import asyncio
import re
from re import Pattern
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import RealDebridError
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.clients.response import AbstractResponse
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://real-debrid.com")
_DB_FLATTEN_URL_KEYS = "parts", "query", "frag"
_API_ENTRYPOINT = AbsoluteHttpURL("https://api.real-debrid.com/rest/1.0")
_ERROR_CODES = {
    -1: "Internal error",
    1: "Missing parameter",
    2: "Bad parameter value",
    3: "Unknown method",
    4: "Method not allowed",
    5: "Slow down",
    6: "Resource unreachable",
    7: "Resource not found",
    8: "Bad token",
    9: "Permission denied",
    10: "Two-Factor authentication needed",
    11: "Two-Factor authentication pending",
    12: "Invalid login",
    13: "Invalid password",
    14: "Account locked",
    15: "Account not activated",
    16: "Unsupported hoster",
    17: "Hoster in maintenance",
    18: "Hoster limit reached",
    19: "Hoster temporarily unavailable",
    20: "Hoster not available for free users",
    21: "Too many active downloads",
    22: "IP Address not allowed",
    23: "Traffic exhausted",
    24: "File unavailable",
    25: "Service unavailable",
    26: "Upload too big",
    27: "Upload error",
    28: "File not allowed",
    29: "Torrent too big",
    30: "Torrent file invalid",
    31: "Action already done",
    32: "Image resolution error",
    33: "Torrent already active",
    34: "Too many requests",
    35: "Infringing file",
    36: "Fair Usage Limit",
}


class RealDebridCrawler(Crawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "real-debrid"
    FOLDER_DOMAIN: ClassVar[str] = "RealDebrid"
    _RATE_LIMIT = 250, 60

    def __post_init__(self) -> None:
        self._api_token = token = self.manager.auth_config.realdebrid.api_key
        self._supported_folder_url_regex: Pattern
        self._supported_url_regex: Pattern
        self.disabled = not bool(token)
        self._headers = {"Authorization": f"Bearer {token}", "User-Agent": "CyberDrop-DL"}

    def is_supported(self, url: AbsoluteHttpURL) -> bool:
        match = self._supported_url_regex.search(str(url))
        return bool(match) or "real-debrid" in url.host

    async def async_startup(self) -> None:
        await self._get_regexes(_API_ENTRYPOINT)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "real-debrid" in scrape_item.url.host and not _is_unrestricted_download(scrape_item.url):
            raise ValueError
        scrape_item.url = _reconstruct_original_url(scrape_item.url)
        if self._is_supported_folder(scrape_item.url):
            return await self.folder(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def _get_regexes(self, *_) -> None:
        if self.disabled:
            return
        try:
            responses: tuple[list[str], list[str]] = await asyncio.gather(
                self._api_request("hosts/regex"),
                self._api_request("hosts/regexFolder"),
            )

            file_regex = [pattern[1:-1] for pattern in responses[0]]
            folder_regex = [pattern[1:-1] for pattern in responses[1]]
            self._supported_url_regex = re.compile("|".join(file_regex + folder_regex))
            self._supported_folder_url_regex = re.compile("|".join(folder_regex))
        except Exception as e:
            log(f"Failed RealDebrid setup: {e}", 40)
            self.disabled = True
            raise

    def _is_supported_folder(self, url: AbsoluteHttpURL) -> bool:
        match = self._supported_folder_url_regex.search(str(url))
        return bool(match)

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        log(f"Scraping folder with RealDebrid: {scrape_item.url}", 20)
        folder_id = _guess_folder(scrape_item.url)
        title = self.create_title(f"{folder_id} [{scrape_item.url.host}]", folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)
        links: list[str] = await self._api_request("unrestrict/folder", link=str(scrape_item.url))
        for link in links:
            new_scrape_item = scrape_item.create_child(self.parse_url(link))
            self.create_task(self.file(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        original_url = scrape_item.url
        if await self.check_complete_from_referer(original_url):
            return

        if _is_unrestricted_download(original_url):
            database_url = debrid_url = original_url
        else:
            host = original_url.host
            title = self.create_title(f"files [{host}]")
            scrape_item.setup_as_album(title)
            password = original_url.query.get("password", "")
            json_resp: dict[str, Any] = await self._api_request(
                "unrestrict/link", link=str(original_url), password=password, remote=False
            )
            debrid_url = self.parse_url(json_resp["download"])
            database_url = _flatten_url(original_url, host)

        if await self.check_complete_from_referer(debrid_url):
            return

        log(f"Real Debrid:\n  Original URL: {original_url}\n  Debrid URL: {debrid_url}", 10)
        filename, ext = self.get_filename_and_ext(debrid_url.name)
        await self.handle_file(database_url, scrape_item, filename, ext, debrid_link=debrid_url)

    async def _api_request(self, path: str, /, **data: Any) -> Any:
        method = "POST" if data else "GET"

        async with self.request(
            _API_ENTRYPOINT / path,
            method=method,
            headers=self._headers,
            data=data or None,
            cache_disabled=True,
        ) as resp:
            return await self._handle_api_response(resp)

    async def _handle_api_response(self, response: AbstractResponse) -> Any:
        if "json" in response.content_type:
            json_resp: dict[str, Any] = await response.json()
            if code := json_resp.get("error_code"):
                code = 7 if code == 16 else code
                msg = _ERROR_CODES.get(code, "Unknown error")
                raise RealDebridError(response.url, code, msg) from None
            else:
                return json_resp

        await self.client.client_manager.check_http_status(response)


def _guess_folder(url: AbsoluteHttpURL) -> str:
    for guess_function in (_guess_folder_by_part, _guess_folder_by_query):
        if folder := guess_function(url):
            return folder
    return url.path


def _guess_folder_by_part(url: AbsoluteHttpURL) -> str | None:
    for word in ("folder", "folders", "dir"):
        try:
            return url.parts[url.parts.index(word) + 1]
        except (IndexError, ValueError):
            continue


def _guess_folder_by_query(url: AbsoluteHttpURL) -> str | None:
    for word in ("sharekey",):
        if folder := url.query.get(word):
            return folder


def _is_unrestricted_download(url: AbsoluteHttpURL) -> bool:
    return any(p in url.host for p in ("download.", "my.")) and "real-debrid" in url.host


def _reconstruct_original_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    """Reconstructs an URL that might have been flatten for the database."""
    if (
        len(url.parts) < 3
        or url.host != PRIMARY_URL.host
        or url.parts[1].count(".") == 0
        or _is_unrestricted_download(url)
    ):
        parsed_url = url

    else:
        parts_dict: dict[str, tuple[str, ...]] = dict.fromkeys(_DB_FLATTEN_URL_KEYS, ())
        key = "parts"
        original_host = url.parts[1]
        for part in url.parts[2:]:
            if part in _DB_FLATTEN_URL_KEYS[1:]:
                key = part
                continue
            parts_dict[key] += (part,)

        path = "/".join(parts_dict["parts"])
        parsed_url = AbsoluteHttpURL(f"https://{original_host}/{path}", encoded="%" in path)
        query_iter = iter(parts_dict["query"])
        if query := tuple(zip(query_iter, query_iter, strict=True)):
            parsed_url = parsed_url.with_query(query)
        if frag := next(iter(parts_dict["frag"]), None):
            parsed_url = parsed_url.with_fragment(frag)
    log(f"Real Debrid:\n Input URL: {url}\n Parsed URL: {parsed_url}")
    return parsed_url


def _flatten_url(original_url: AbsoluteHttpURL, host: str) -> AbsoluteHttpURL:
    """Some hosts use query params or fragment as id or password (ex: mega.nz)
    This function flattens the query and fragment as parts of the URL path because database lookups only use the url path"""
    flatten_url = PRIMARY_URL / host / original_url.path[1:]
    if original_url.query:
        query_params = (item for pair in original_url.query.items() for item in pair)
        flatten_url = flatten_url / "query" / "/".join(query_params)

    if original_url.fragment:
        flatten_url = flatten_url / "frag" / original_url.fragment

    return flatten_url
