from __future__ import annotations

import base64
import calendar
import datetime
import json
import math
import re
from dataclasses import dataclass
from functools import partial
from itertools import cycle
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable

    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

BASE_CDNS = [
    "bacon",
    "big-taco",
    "burger",
    "c",
    "cdn",
    "fries",
    "kebab",
    "meatballs",
    "milkshake",
    "nachos",
    "nugget",
    "pizza",
    "ramen",
    "soup",
    "taquito",
    "wiener",
    "wings",
    r"mlk-bk\.cdn\.gigachad-cdn",
]

DOWNLOAD_API_ENTRYPOINT = URL("https://get.bunkrr.su/api/vs")
DOWNLOAD_API_ENTRYPOINT = URL("https://get.bunkrr.su/api/_001")
STREAMING_API_ENTRYPOINT = URL("https://bunkr.site/api/vs")

EXTENDED_CDNS = [f"cdn-{cdn}" for cdn in BASE_CDNS]
IMAGE_CDNS = [f"i-{cdn}" for cdn in BASE_CDNS]
CDNS = BASE_CDNS + EXTENDED_CDNS + IMAGE_CDNS
CDN_REGEX_STR = r"^(?:(?:(" + "|".join(CDNS) + r")[0-9]{0,2}(?:redir)?))\.bunkr?\.[a-z]{2,3}$"
CDN_POSSIBILITIES = re.compile(CDN_REGEX_STR)

ALBUM_ITEM_SELECTOR = "div[class*='relative group/item theItem']"
ITEM_NAME_SELECTOR = "p[class*='theName']"
ITEM_DATE_SELECTOR = 'span[class*="theDate"]'
DOWNLOAD_BUTTON_SELECTOR = "a.btn.ic-download-01"
IMAGE_PREVIEW_SELECTOR = "img.max-h-full.w-auto.object-cover.relative"
VIDEO_SELECTOR = "video > source"
VIDEO_AND_IMAGE_EXTS = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"]


class ApiResponse(NamedTuple):
    encrypted: bool
    timestamp: int
    url: str


@dataclass(frozen=True)
class AlbumItem:
    name: str
    thumbnail: str
    date: int
    url: URL

    @classmethod
    def from_tag(cls, tag: Tag, parse_url: Callable[..., URL]) -> AlbumItem:
        name = tag.select_one(ITEM_NAME_SELECTOR).text  # type: ignore
        thumbnail: str = tag.select_one("img").get("src")  # type: ignore
        date_str = tag.select_one(ITEM_DATE_SELECTOR).text.strip()  # type: ignore
        date = parse_datetime(date_str)
        link_str: str = tag.find("a").get("href")  # type: ignore
        link = parse_url(link_str)
        return cls(name, thumbnail, date, link)

    def get_src(self, parse_url: Callable[..., URL]) -> URL:
        src_str = self.thumbnail.replace("/thumbs/", "/")
        src = parse_url(src_str)
        src = with_suffix_encoded(src, self.suffix).with_query(None)
        if src.suffix.lower() not in FILE_FORMATS["Images"]:
            src = src.with_host(src.host.replace("i-", ""))  # type: ignore
        return override_cdn(src)

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix


class BunkrrCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"bunkrr": ["bunkrr", "bunkr"]}
    primary_base_domain = URL("https://bunkr.site")

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "Bunkrr")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

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
        """Scrapes an album."""
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        album_id = scrape_item.url.parts[2]
        title = soup.select_one("title").text.rsplit(" | Bunkr")[0].strip()  # type: ignore
        title = self.create_title(title, album_id)
        scrape_item.setup_as_album(title)
        scrape_item.album_id = album_id
        results = await self.get_album_results(album_id)

        item_tags: list[Tag] = soup.select(ALBUM_ITEM_SELECTOR)
        parse_url = partial(self.parse_url, relative_to=scrape_item.url.with_path("/"))

        for tag in item_tags:
            item = AlbumItem.from_tag(tag, parse_url)
            new_scrape_item = scrape_item.create_child(item.url, possible_datetime=item.date)
            await self.process_album_item(new_scrape_item, item, results)
            scrape_item.add_children()

    @error_handling_wrapper
    async def process_album_item(self, scrape_item: ScrapeItem, item: AlbumItem, results: dict) -> None:
        link = item.get_src(self.parse_url)
        if link.suffix.lower() not in VIDEO_AND_IMAGE_EXTS or "no-image" in link.name or self.deep_scrape(link):
            self.manager.task_group.create_task(self.file(scrape_item))
            return

        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".mp4")
        custom_filename, _ = self.get_filename_and_ext(item.name, assume_ext=".mp4")
        if not self.check_album_results(link, results):
            await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file from a streaming URL."""
        soup = link = date = None  # type: ignore
        if is_stream_redirect(scrape_item.url):
            soup, scrape_item.url = await self.client.get_soup_and_return_url(self.domain, scrape_item.url)

        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)
        if await self.check_complete_from_referer(scrape_item):
            return

        if not soup:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        image_container = soup.select_one(IMAGE_PREVIEW_SELECTOR)
        download_link_container = soup.select_one(DOWNLOAD_BUTTON_SELECTOR)

        # Try image first to not make any aditional request
        if image_container:
            link_str: str = image_container.get("src")  # type: ignore
            link = self.parse_url(link_str)

        # Try to get downloadd URL from streaming API. Should work for most files, even none video files
        if not link and "f" in scrape_item.url.parts:
            link = await self.get_download_url_from_api(scrape_item.url)

        # Fallback for everything else, try to get the download URL. `handle_direct_link` will make the final request to the API
        if not link and download_link_container:
            link_str: str = download_link_container.get("href")  # type: ignore
            link = self.parse_url(link_str)

        # Everything failed, abort
        if not link:
            raise ScrapeError(422, "Could not find source")

        if not scrape_item.possible_datetime:
            date_str = soup.select_one(ITEM_DATE_SELECTOR)
            if date_str:
                date = parse_datetime(date_str.text.strip())
                scrape_item.possible_datetime = date

        title: str = soup.select_one("h1").text.strip()  # type: ignore
        await self.handle_direct_link(scrape_item, link, fallback_filename=title)

    @error_handling_wrapper
    async def reinforced_file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file from a reinforced URL.

        Gets the filename from the soup before sending the scrape_item to `handle_direct_link`"""
        soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title: str = soup.select_one("h1").text.strip()  # type: ignore
        link: URL = await self.get_download_url_from_api(scrape_item.url)
        await self.handle_direct_link(scrape_item, link, fallback_filename=title)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL, fallback_filename: str = "") -> None:
        """Handles direct links (CDNs URLs) before sending them to the downloader.

        `fallback_filename` will only be used if the link has no `n` query parameter"""

        link = url

        if is_reinforced_link(link):
            scrape_item.url = link
            link = await self.get_download_url_from_api(link)

        link = override_cdn(link)

        try:
            filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            filename, ext = self.get_filename_and_ext(scrape_item.url.name, assume_ext=".mp4")

        custom_filename: str = link.query.get("n") or fallback_filename
        custom_filename, _ = self.get_filename_and_ext(custom_filename)

        if is_cdn(scrape_item.url) and not is_reinforced_link(scrape_item.url):
            scrape_item.url = URL("https://get.bunkr.su/")  # Using a CDN as referer gets a 403 response

        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    async def get_download_url_from_api(self, url: URL) -> URL:
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

        data = json.dumps(data_dict)
        async with self.request_limiter:
            json_resp: dict = await self.client.post_data(self.domain, api_url, data=data, headers_inc=headers)

        api_response = ApiResponse(**json_resp)
        link_str = decrypt_api_response(api_response)
        return self.parse_url(link_str)

    def deep_scrape(self, url: URL) -> bool:
        assert url.host
        return any(part in url.host.split(".") for part in ("burger",)) or self.manager.config_manager.deep_scrape

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_part_next_to(url: URL, part: str) -> str:
    part_index = url.parts.index(part) + 1
    return url.parts[part_index]


def is_stream_redirect(url: URL) -> bool:
    assert url.host
    first_subdomain = url.host.split(".")[0]
    prefix, _, number = first_subdomain.partition("cdn")
    if not prefix and number.isdigit():
        return True
    return any(part in url.host for part in ("cdn12", "cdn-")) or url.host == "cdn.bunkr.ru"


def is_cdn(url: URL) -> bool:
    """Checks if a given URL is from a CDN."""
    assert url.host
    return bool(CDN_POSSIBILITIES.match(url.host))


def override_cdn(url: URL) -> URL:
    assert url.host
    if "milkshake" in url.host:
        return url.with_host("mlk-bk.cdn.gigachad-cdn.ru")
    return url


def is_reinforced_link(url: URL) -> bool:
    assert url.host
    return any(part in url.host.split(".") for part in ("get",)) and "file" in url.parts


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%H:%M:%S %d/%m/%Y")
    return calendar.timegm(parsed_date.timetuple())


def with_suffix_encoded(url: URL, suffix: str) -> URL:
    name = Path(url.raw_name).with_suffix(suffix)
    return url.parent.joinpath(str(name), encoded=True).with_query(url.query).with_fragment(url.fragment)


def decrypt_api_response(api_response: ApiResponse) -> str:
    if not api_response.encrypted:
        return api_response.url

    time_key = math.floor(api_response.timestamp / 3600)
    secret_key = f"SECRET_KEY_{time_key}"
    byte_array = bytearray(base64.b64decode(api_response.url))
    return xor_decrypt(byte_array, secret_key)


def xor_decrypt(encrypted_data: bytearray, key: str) -> str:
    key_bytes = key.encode("utf-8")
    decrypted_data = bytearray(b_input ^ b_key for b_input, b_key in zip(encrypted_data, cycle(key_bytes)))
    return decrypted_data.decode("utf-8", errors="ignore")
