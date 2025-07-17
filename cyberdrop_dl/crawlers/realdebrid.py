from __future__ import annotations

import asyncio
import re
from re import Pattern
from typing import TYPE_CHECKING, ClassVar

from multidict import MultiDict

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.managers.real_debrid.api import RealDebridAPI
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://real-debrid.com")
_FOLDER_AS_PART = {"folder", "folders", "dir"}
_FOLDER_AS_QUERY = {"sharekey"}
_DB_ENCODE_PARTS = "parts", "query", "frag"


class RealDebridCrawler(Crawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "real-debrid"
    FOLDER_DOMAIN: ClassVar[str] = "RealDebrid"

    def __post_init__(self) -> None:
        self._headers = {}
        self._api_token = self.manager.auth_config.realdebrid.api_key
        self._file_regex: Pattern
        self._supported_folder_url_regex: Pattern
        self._supported_url_regex: Pattern
        self._api: RealDebridAPI
        self.disabled = not bool(self._api_token)

    async def async_startup(self) -> None:
        self._api = RealDebridAPI(self._api_token, self.client._session)
        await self._get_supported_urls_regexes()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = _decode_original_url(scrape_item.url)
        if self._is_supported_folder(scrape_item.url):
            return await self.folder(scrape_item)
        await self.file(scrape_item)

    async def _get_supported_urls_regexes(self) -> None:
        if self.disabled:
            return
        try:
            files_r, folders_r = await asyncio.gather(self._api.hosts.regex(), self._api.hosts.regex_folder())
            file_regex = [pattern[1:-1] for pattern in files_r]
            folder_regex = [pattern[1:-1] for pattern in folders_r]
            file_or_folder_regex = "|".join(file_regex + folder_regex)
            folder_regex = "|".join(folder_regex)
            self._supported_url_regex = re.compile(file_or_folder_regex)
            self._supported_folder_url_regex = re.compile(folder_regex)
        except Exception as e:
            log(f"Failed RealDebrid setup: {e}", 40)
            self.disabled = True

    def _is_supported_folder(self, url: AbsoluteHttpURL) -> bool:
        match = self._supported_folder_url_regex.search(str(url))
        return bool(match)

    def is_supported(self, url: AbsoluteHttpURL) -> bool:
        match = self._supported_url_regex.search(str(url))
        return bool(match) or "real-debrid" in url.host.lower()

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        self.log(f"Scraping folder with RealDebrid: {scrape_item.url}", 20)
        folder_id = _guess_folder(scrape_item.url)
        title = self.create_title(f"{folder_id} [{scrape_item.url.host.lower()}]", folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)
        links = await self._api.unrestrict.folder(scrape_item.url)
        for link in links:
            new_scrape_item = scrape_item.create_child(link)
            self.create_task(self.file(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        original_url = scrape_item.url
        password = original_url.query.get("password", "")
        if await self.check_complete_from_referer(original_url):
            return

        if _is_self_hosted_download(scrape_item.url):
            database_url = debrid_url = scrape_item.url
        else:
            host = original_url.host.lower()
            title = self.create_title(f"files [{host}]")
            scrape_item.setup_as_album(title)
            debrid_url = await self._api.unrestrict.link(original_url, password)
            database_url = _encode_url_for_db(original_url, host)

        if await self.check_complete_from_referer(debrid_url):
            return

        self.log(f"Real Debrid:\n  Original URL: {original_url}\n  Debrid URL: {debrid_url}", 10)
        filename, ext = self.get_filename_and_ext(debrid_url.name)
        await self.handle_file(database_url, scrape_item, filename, ext, debrid_link=debrid_url)


def _guess_folder(url: AbsoluteHttpURL) -> str:
    for guess_function in (_guess_folder_by_part, _guess_folder_by_query):
        if folder := guess_function(url):
            return folder
    return url.path


def _guess_folder_by_part(url: AbsoluteHttpURL) -> str | None:
    for word in _FOLDER_AS_PART:
        if word in url.parts:
            index = url.parts.index(word)
            if index + 1 < len(url.parts):
                return url.parts[index + 1]


def _guess_folder_by_query(url: AbsoluteHttpURL) -> str | None:
    for word in _FOLDER_AS_QUERY:
        folder = url.query.get(word)
        if folder:
            return folder


def _is_self_hosted_download(url: AbsoluteHttpURL) -> bool:
    return any(subdomain in url.host for subdomain in ("download.", "my.")) and "real-debrid" in url.host


def _decode_original_url(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    """Reconstructs an URL that might have been encoded for database."""
    log(f"Input URL: {url}")
    if len(url.parts) < 3 or url.host != PRIMARY_URL.host or url.parts[1].count(".") == 0:
        log(f"Parsed URL: {url}")
        return url

    parts_dict: dict[str, tuple[str, ...]] = dict.fromkeys(_DB_ENCODE_PARTS, ())
    key = "parts"

    original_domain = url.parts[1]
    for part in url.parts[2:]:
        if part in ("query", "frag"):
            key = part
            continue
        parts_dict[key] += (part,)

    path = "/".join(parts_dict["parts"])
    query = MultiDict()
    for i in range(0, len(parts_dict["query"]), 2):
        query[parts_dict["query"][i]] = parts_dict["query"][i + 1]
    query = query or None
    frag = next(iter(parts_dict["frag"]), "")
    parsed_url = (
        AbsoluteHttpURL(f"https://{original_domain}/{path}", encoded="%" in path).with_query(query).with_fragment(frag)
    )
    log(f"Parsed URL: {parsed_url}")
    return parsed_url


def _encode_url_for_db(original_url: AbsoluteHttpURL, host: str) -> AbsoluteHttpURL:
    # Some hosts use query params or fragment as id or password (ex: mega.nz)
    # This save the query and fragment as parts of the URL path because database lookups only use the url path
    flatten_url = PRIMARY_URL / host / original_url.path[1:]
    if original_url.query:
        query_params_list = [item for pair in original_url.query.items() for item in pair]
        flatten_url = flatten_url / "query" / "/".join(query_params_list)

    if original_url.fragment:
        flatten_url = flatten_url / "frag" / original_url.fragment

    return flatten_url
