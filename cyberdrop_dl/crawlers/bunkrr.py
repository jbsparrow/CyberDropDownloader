from __future__ import annotations

import asyncio
import base64
import itertools
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from aiohttp import ClientConnectorError

from cyberdrop_dl.constants import FILE_FORMATS
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DDOSGuardError, NoExtensionError, ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
    get_text_between,
    parse_url,
    with_suffix_encoded,
    xor_decrypt,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


# CDNs
BASE_CDNS = [
    "bacon",
    "beer",
    "big-taco",
    "burger",
    "c",
    "cdn",
    "cheese",
    "fries",
    "kebab",
    "meatballs",
    "milkshake",
    "nachos",
    "nugget",
    "pizza",
    "ramen",
    "rice",
    "soup",
    "sushi",
    "taquito",
    "wiener",
    "wings",
    "maple",
    r"mlk-bk\.cdn\.gigachad-cdn",
]
EXTENDED_CDNS = [f"cdn-{cdn}" for cdn in BASE_CDNS]
IMAGE_CDNS = [f"i-{cdn}" for cdn in BASE_CDNS]
CDNS = BASE_CDNS + EXTENDED_CDNS + IMAGE_CDNS
CDN_POSSIBILITIES = re.compile(r"^(?:(?:(" + "|".join(CDNS) + r")[0-9]{0,2}(?:redir)?))\.bunkr?\.[a-z]{2,3}$")

# URLs
DOWNLOAD_API_ENTRYPOINT = AbsoluteHttpURL("https://apidl.bunkr.ru/api/_001_v2")
STREAMING_API_ENTRYPOINT = AbsoluteHttpURL("https://bunkr.site/api/vs")
PRIMARY_URL = AbsoluteHttpURL("https://bunkr.site")


class Selectors:
    ALBUM_ITEM = "div[class*='relative group/item theItem']"
    ITEM_NAME = "p[class*='theName']"
    ITEM_DATE = 'span[class*="theDate"]'
    DOWNLOAD_BUTTON = "a.btn.ic-download-01"
    THUMBNAIL = 'img[alt="image"]'
    IMAGE_PREVIEW = "img.max-h-full.w-auto.object-cover.relative"
    VIDEO = "video > source"
    JS_SLUG = "script:contains('jsSlug')"
    NEXT_PAGE = "nav.pagination a[href]:contains('»')"


_SELECTORS = Selectors()
VIDEO_AND_IMAGE_EXTS: set[str] = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"]
HOST_OPTIONS: set[str] = {"bunkr.site", "bunkr.cr", "bunkr.ph"}
known_bad_hosts: set[str] = set()


class ApiResponse(NamedTuple):
    encrypted: bool
    timestamp: int
    url: str


@dataclass(frozen=True)
class AlbumItem:
    name: str
    thumbnail: str
    date: str
    path_qs: str

    @staticmethod
    def from_tag(tag: Tag) -> AlbumItem:
        name = css.select_one_get_text(tag, _SELECTORS.ITEM_NAME)
        thumbnail: str = css.select_one_get_attr(tag, _SELECTORS.THUMBNAIL, "src")
        date_str = css.select_one_get_text(tag, _SELECTORS.ITEM_DATE)
        path_qs: str = css.select_one_get_attr(tag, "a", "href")
        return AlbumItem(name, thumbnail, date_str, path_qs)

    @property
    def src(self) -> AbsoluteHttpURL:
        src_str = self.thumbnail.replace("/thumbs/", "/")
        src = parse_url(src_str, relative_to=PRIMARY_URL)
        src = with_suffix_encoded(src, self.suffix).with_query(None)
        if src.suffix.lower() not in FILE_FORMATS["Images"]:
            src = src.with_host(src.host.replace("i-", ""))
        return override_cdn(src)

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix


class BunkrrCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "bunkr", "bunkrr"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/...",
        "Video": "/v/...",
        "File": "/f/...",
        "Direct links": "",
    }
    DATABASE_PRIMARY_HOST: ClassVar[str] = "bunkr.site"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL(f"https://{DATABASE_PRIMARY_HOST}")
    DOMAIN: ClassVar[str] = "bunkrr"

    def __post_init__(self) -> None:
        self.known_good_host: str = ""
        self.switch_host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @property
    def known_good_url(self) -> AbsoluteHttpURL | None:
        if self.known_good_host:
            return AbsoluteHttpURL(f"https://{self.known_good_host}")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if is_reinforced_link(scrape_item.url):  #  get.bunkr.su/file/<file_id>
            return await self.reinforced_file(scrape_item)
        if "a" in scrape_item.url.parts:  #  bunkr.site/a/<album_id>
            return await self.album(scrape_item)
        if is_cdn(scrape_item.url) and not is_stream_redirect(scrape_item.url):  # kebab.bunkr.su/<uuid>
            return await self.handle_direct_link(scrape_item, scrape_item.url, fallback_filename=scrape_item.url.name)
        # bunkr.su/f/<filename>, bunkr.su/f/<file_slug>, bunkr.su/<short_file_id> or cdn.bunkr.su/<file_id> (stream redirect)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_id = scrape_item.url.parts[2]
        title: str = ""
        results = await self.get_album_results(album_id)

        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = css.page_title(soup, "bunkr")
                title = self.create_title(title, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)

            for tag in soup.select(_SELECTORS.ALBUM_ITEM):
                item = AlbumItem.from_tag(tag)
                link = self.parse_url(item.path_qs, relative_to=scrape_item.url.origin())
                new_scrape_item = scrape_item.create_child(
                    link, possible_datetime=self.parse_date(item.date, "%H:%M:%S %d/%m/%Y")
                )
                self.create_task(self._process_album_item_task(new_scrape_item, item, results))
                scrape_item.add_children()

    async def web_pager(
        self,
        url: AbsoluteHttpURL,
        next_page_selector: str | None = None,
        *,
        cffi: bool = False,
        **kwargs: Any,
    ) -> AsyncGenerator[BeautifulSoup]:
        page_url = url
        init_page = int(url.query.get("page") or 1)
        for page in itertools.count(init_page):
            soup = await self.get_soup_lenient(page_url.with_query(page=page))
            yield soup
            has_next_page = soup.select_one(_SELECTORS.NEXT_PAGE)
            if not has_next_page:
                break

    @error_handling_wrapper
    async def _process_album_item(self, scrape_item: ScrapeItem, item: AlbumItem, results: dict) -> None:
        link = item.src
        if link.suffix.lower() not in VIDEO_AND_IMAGE_EXTS or "no-image" in link.name or self.deep_scrape(link):
            self.create_task(self.run(scrape_item))
            return

        if self.check_album_results(link, results):
            return
        if not link.query.get("n"):
            link = link.update_query(n=item.name)

        custom_filename, ext = self.get_filename_and_ext(link.query["n"], assume_ext=".mp4")

        try:
            filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            # custom_filename did not raise an exception, so we ignore here as well
            filename, ext = self.get_filename_and_ext(str(Path(link.name).with_suffix(ext)))

        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    _process_album_item_task = auto_task_id(_process_album_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        link: AbsoluteHttpURL | None = None
        soup: BeautifulSoup | None = None
        if is_stream_redirect(scrape_item.url):
            response, soup = await self.client._get_response_and_soup(self.DOMAIN, scrape_item.url)
            scrape_item.url = AbsoluteHttpURL(response.url)
            del response

        database_url = scrape_item.url.with_host(self.DATABASE_PRIMARY_HOST)
        if await self.check_complete_from_referer(database_url):
            return

        if not soup:
            soup = await self.get_soup_lenient(scrape_item.url)

        image_container = soup.select_one(_SELECTORS.IMAGE_PREVIEW)
        download_link_container = soup.select_one(_SELECTORS.DOWNLOAD_BUTTON)

        # Try image first to not make any aditional request
        if image_container:
            link_str: str = css.get_attr(image_container, "src")
            link = self.parse_url(link_str)

        # Try to get downloadd URL from streaming API. Should work for most files, even none video files
        if not link and "f" in scrape_item.url.parts:
            slug = get_slug_from_soup(soup) or scrape_item.url.name or scrape_item.url.parent.name
            base = self.known_good_url or scrape_item.url.origin()
            slug_url = base / "f" / slug.encode().decode("unicode-escape")
            link = await self.get_download_url_from_api(slug_url)

        # Fallback for everything else, try to get the download URL. `handle_direct_link` will make the final request to the API
        if not link and download_link_container:
            link_str: str = css.get_attr(download_link_container, "href")
            link = self.parse_url(link_str)

        # Everything failed, abort
        if not link:
            raise ScrapeError(422, "Could not find source")

        if not scrape_item.possible_datetime and (date_str := soup.select_one(_SELECTORS.ITEM_DATE)):
            scrape_item.possible_datetime = self.parse_date(date_str.text.strip())

        title = open_graph.title(soup)  # See: https://github.com/jbsparrow/CyberDropDownloader/issues/929
        await self.handle_direct_link(scrape_item, link, fallback_filename=title)

    @error_handling_wrapper
    async def reinforced_file(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        title: str = css.select_one_get_text(soup, "h1")
        link: AbsoluteHttpURL | None = await self.get_download_url_from_api(scrape_item.url)
        if not link:
            raise ScrapeError(422)
        await self.handle_direct_link(scrape_item, link, fallback_filename=title)

    @error_handling_wrapper
    async def handle_direct_link(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL, fallback_filename: str = ""
    ) -> None:
        """Handles direct links (CDNs URLs) before sending them to the downloader.

        `fallback_filename` will only be used if the link has no `n` query parameter"""

        link = url
        if is_reinforced_link(link):
            scrape_item.url = link
            link = await self.get_download_url_from_api(link)

        if not link:
            raise ScrapeError(422)

        link = override_cdn(link)

        if not link.query.get("n"):
            link = link.update_query(n=fallback_filename)

        # Bunkr is a special case.
        # It should NOT use `create_custom_filename` since the custom file name is actually used to validate the ext
        custom_filename, ext = self.get_filename_and_ext(link.query["n"], assume_ext=".mp4")
        try:
            filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            # custom_filename did not raise an exception, so we ignore here as well
            filename, ext = self.get_filename_and_ext(str(Path(link.name).with_suffix(ext)))

        if is_cdn(scrape_item.url) and not is_reinforced_link(scrape_item.url):
            scrape_item.url = AbsoluteHttpURL("https://get.bunkr.su/")  # Using a CDN as referer gets a 403 response

        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def get_download_url_from_api(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        """Gets the download link for a given URL

        1. Reinforced URL (get.bunkr.su/<file_id>). or
        2. Streaming URL (bunkr.site/f/<file_slug>)"""

        api_url = DOWNLOAD_API_ENTRYPOINT
        headers = {"Referer": str(url), "Content-Type": "application/json"}
        if is_reinforced_link(url):
            data_dict = {"id": get_part_next_to(url, "file")}
        else:
            data_dict = {"slug": get_part_next_to(url, "f")}
            api_url = STREAMING_API_ENTRYPOINT
            if self.known_good_host:
                api_url = STREAMING_API_ENTRYPOINT.with_host(self.known_good_host)

        data = json.dumps(data_dict)
        async with self.request_limiter:
            json_resp: dict = await self.client.post_data(self.DOMAIN, api_url, data=data, headers=headers)

        api_response = ApiResponse(**json_resp)
        link_str = decrypt_api_response(api_response)
        link = self.parse_url(link_str)
        if link != PRIMARY_URL:  # We got an empty response
            return link

    def deep_scrape(self, url: AbsoluteHttpURL) -> bool:
        return any(part in url.host.split(".") for part in ("burger.",)) or self.manager.config_manager.deep_scrape

    async def handle_file(
        self,
        url: AbsoluteHttpURL,
        scrape_item: ScrapeItem,
        filename: str,
        ext: str,
        *,
        custom_filename: str | None = None,
        debrid_link: AbsoluteHttpURL | None = None,
    ) -> None:
        """Overrides primary host before before calling base crawler's `handle_file`"""
        if is_root_domain(scrape_item.url):
            scrape_item.url = scrape_item.url.with_host(self.DATABASE_PRIMARY_HOST)
        await super().handle_file(
            url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=debrid_link
        )

    async def get_soup_lenient(self, url: AbsoluteHttpURL) -> BeautifulSoup:
        """Overrides URL in host if we know a valid host.

        If we don't know a valid host but the response was successful, register the host as a valid host"""

        async def get_soup(url: AbsoluteHttpURL) -> BeautifulSoup:
            async with self.request_limiter:
                return await self.client.get_soup(self.DOMAIN, url)

        async def get_soup_no_error(url: AbsoluteHttpURL) -> BeautifulSoup | None:
            global known_bad_hosts
            try:
                soup: BeautifulSoup = await get_soup(url)
            except (ClientConnectorError, DDOSGuardError):
                known_bad_hosts.add(url.host)
                if not HOST_OPTIONS - known_bad_hosts:
                    raise
            else:
                if not self.known_good_host:
                    self.known_good_host = url.host
                return soup

        if not is_root_domain(url):
            return await get_soup(url)

        elif self.known_good_host:
            return await get_soup(url.with_host(self.known_good_host))

        async with self.switch_host_locks[url.host]:
            if url.host not in known_bad_hosts:
                soup = await get_soup_no_error(url)
                if soup:
                    return soup

        for host in HOST_OPTIONS - known_bad_hosts:
            async with self.switch_host_locks[host]:
                if host not in known_bad_hosts:
                    soup = await get_soup_no_error(url.with_host(host))
                    if soup:
                        return soup

        # everything failed, do the request with the original URL to throw an exception
        return await get_soup(url)


def get_part_next_to(url: AbsoluteHttpURL, part: str) -> str:
    part_index = url.parts.index(part) + 1
    return url.parts[part_index]


def is_stream_redirect(url: AbsoluteHttpURL) -> bool:
    first_subdomain = url.host.split(".")[0]
    prefix, _, number = first_subdomain.partition("cdn")
    if not prefix and number.isdigit():
        return True
    return any(part in url.host for part in ("cdn12", "cdn-")) or url.host == "cdn.bunkr.ru"


def is_cdn(url: AbsoluteHttpURL) -> bool:
    return bool(CDN_POSSIBILITIES.match(url.host))


def override_cdn(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    if "milkshake" in url.host:
        return url.with_host("mlk-bk.cdn.gigachad-cdn.ru")
    return url


def is_reinforced_link(url: AbsoluteHttpURL) -> bool:
    return url.host.startswith("get.") and "file" in url.parts


def decrypt_api_response(api_response: ApiResponse) -> str:
    if not api_response.encrypted:
        return api_response.url

    time_key = math.floor(api_response.timestamp / 3600)
    secret_key = f"SECRET_KEY_{time_key}"
    encrypted_url = base64.b64decode(api_response.url)
    return xor_decrypt(encrypted_url, secret_key.encode())


def get_slug_from_soup(soup: BeautifulSoup) -> str | None:
    info_js = soup.select_one(_SELECTORS.JS_SLUG)
    if not info_js:
        return
    return get_text_between(info_js.text, "jsSlug = '", "';")


def is_root_domain(url: AbsoluteHttpURL) -> bool:
    return "bunkr" in url.host and url.host.count(".") == 1
