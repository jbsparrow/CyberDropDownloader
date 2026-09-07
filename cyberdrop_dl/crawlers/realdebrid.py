"""https://api.real-debrid.com"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar, override

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.constants import CDL_USER_AGENT
from cyberdrop_dl.crawlers.crawler import API, Crawler
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://real-debrid.com")
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


@HTTPConfig(rate_limit=(250, 60))
@HTTPConfig.default_headers(user_agent=CDL_USER_AGENT)
class RealDebridCrawler(Crawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "real-debrid"
    FOLDER_DOMAIN: ClassVar[str] = "RealDebrid"

    @override
    def __json_resp_check__(self, json_resp: dict[str, Any], _) -> None:
        if code := json_resp.get("error_code"):
            code = 7 if code == 16 else code
            msg = _ERROR_CODES.get(code, "Unknown error").capitalize()
            ui_failure = f"RealDebrid Error ({code})"
            raise ScrapeError(ui_failure, msg)

    def __post_init__(self) -> None:
        token = self.config.auth.real_debrid.api_key
        self.disabled = not bool(token)
        self.api: RealDebridAPI = RealDebridAPI.from_crawler(self)
        self.api.token = token

    async def __async_post_init__(self) -> None:
        await self._get_regexes()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "real-debrid" in scrape_item.url.host:
            if URLParser.is_unrestricted_download(scrape_item.url):
                return await self.direct_file(scrape_item)
            raise ValueError

        if self.api.is_supported_folder(scrape_item.url):
            return await self.folder(scrape_item)
        await self.file(scrape_item)

    async def _get_regexes(self) -> None:
        if self.disabled:
            return

        with self.catch_errors(self.api.ENTRYPOINT), self.disable_on_error("Setup failed. Unable to get URL regex"):
            await self.api.connect()

    @error_handling_wrapper
    async def folder(self, scrape_item: ScrapeItem) -> None:
        folder_id = URLParser.guess_folder_id(scrape_item.url)
        title = self.create_title(f"{folder_id} [{scrape_item.url.host}]", folder_id)
        scrape_item.setup_as_album(title, album_id=folder_id)
        links: list[str] = await self.api.unrestrict_folder(scrape_item.url)
        for link in links:
            new_scrape_item = scrape_item.create_child(self.parse_url(link))
            self.create_eager_task(self.file(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        url = scrape_item.url
        if await self.check_complete_from_referer(scrape_item.url):
            return

        title = self.create_title(f"files [{url.host}]")
        scrape_item.setup_as_album(title)
        debrid_link = await self.api.unrestrict(url, scrape_item.password)
        self.log.info(f"\n  Original URL: {url}\n  Debrid URL: {debrid_link}")
        filename, ext = self.get_filename_and_ext(debrid_link.name)
        await self.handle_file(
            url,
            scrape_item,
            debrid_link.name,
            ext,
            debrid_link=debrid_link,
            custom_filename=filename,
        )


class RealDebridAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.real-debrid.com/rest/1.0")
    _folder_regex: re.Pattern[str]
    _file_regex: re.Pattern[str]
    token: str | None

    def is_supported(self, url: AbsoluteHttpURL) -> bool:
        match = self._file_regex.search(str(url))
        return bool(match) or "real-debrid" in url.host or self.is_supported_folder(url)

    def is_supported_folder(self, url: AbsoluteHttpURL) -> bool:
        return bool(self._folder_regex.search(str(url)))

    async def connect(self) -> None:
        responses: tuple[list[str], list[str]] = await aio.gather(
            self._request("hosts/regex"),
            self._request("hosts/regexFolder"),
            fail_fast=False,
        )

        file_regex = (pattern[1:-1] for pattern in responses[0])
        folder_regex = (pattern[1:-1] for pattern in responses[1])
        self._file_regex = re.compile("|".join(file_regex))
        self._folder_regex = re.compile("|".join(folder_regex))

    async def unrestrict(self, url: AbsoluteHttpURL, password: str | None) -> AbsoluteHttpURL:
        resp: dict[str, Any] = await self._request("unrestrict/link", link=url, password=password, remote=False)
        return self.parse_url(resp["download"])

    async def unrestrict_folder(self, url: AbsoluteHttpURL) -> list[str]:
        return await self._request("unrestrict/folder", url)

    async def _request(self, path: str, /, link: AbsoluteHttpURL | None = None, **data: Any) -> Any:
        if link:
            data["link"] = str(link)

        return await self.request_json(
            self.ENTRYPOINT / path,
            "POST" if data else "GET",
            headers={"Authorization": f"Bearer {self.token}"},
            data=data or None,
        )


# TODO: delete this entire class in v9. Save URLs in the database as is. Move this logic to a transfer module
class URLParser:
    _DB_FLATTEN_URL_KEYS = "parts", "query", "frag"

    @classmethod
    def guess_folder_id(cls, url: AbsoluteHttpURL) -> str:
        for word in ("folder", "folders", "dir"):
            try:
                return url.parts[url.parts.index(word) + 1]
            except (IndexError, ValueError):
                continue

        for word in ("sharekey",):
            if folder := url.query.get(word):
                return folder

        return url.path

    @classmethod
    def is_unrestricted_download(cls, url: AbsoluteHttpURL) -> bool:
        return any(p in url.host for p in ("download.", "my.")) and "real-debrid" in url.host

    @classmethod
    def reconstruct_original_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        """Reconstructs an URL that might have been flatten for the database."""
        if (
            len(url.parts) < 3
            or url.host != _PRIMARY_URL.host
            or url.parts[1].count(".") == 0
            or cls.is_unrestricted_download(url)
        ):
            return url

        parts_dict: dict[str, tuple[str, ...]] = dict.fromkeys(cls._DB_FLATTEN_URL_KEYS, ())
        key = "parts"
        original_host = url.parts[1]
        for part in url.parts[2:]:
            if part in cls._DB_FLATTEN_URL_KEYS[1:]:
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

        return parsed_url

    @classmethod
    def flatten_url(cls, original_url: AbsoluteHttpURL, host: str) -> AbsoluteHttpURL:
        """Some hosts use query params or fragment as id or password (ex: mega.nz)
        This function flattens the query and fragment as parts of the URL path because database lookups only use the url path"""
        flatten_url = _PRIMARY_URL / host / original_url.path[1:]
        if original_url.query:
            query_params = (item for pair in original_url.query.items() for item in pair)
            flatten_url = flatten_url / "query" / "/".join(query_params)

        if original_url.fragment:
            flatten_url = flatten_url / "frag" / original_url.fragment

        return flatten_url
