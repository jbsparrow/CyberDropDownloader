from __future__ import annotations

import base64
import calendar
import datetime
import json
import math
import re
from dataclasses import dataclass
from functools import partial
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

API_ENTRYPOINT = URL("https://get.bunkrr.su/api/vs")

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
        scrape_item.url = await self.get_final_url(scrape_item)
        if not scrape_item.url:
            return

        if "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        elif is_cdn(scrape_item.url) and not is_stream_redirect(scrape_item.url):
            await self.handle_direct_link(scrape_item, fallback_filename=scrape_item.url.name)
        else:
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
        scrape_item.setup_as_album(title, album_id=album_id)

        item_tags: list[Tag] = soup.select(ALBUM_ITEM_SELECTOR)
        parse_url = partial(self.parse_url, relative_to=scrape_item.url.with_path("/"))

        for tag in item_tags:
            item = AlbumItem.from_tag(tag, parse_url)
            new_scrape_item = scrape_item.create_child(item.url, possible_datetime=item.date)
            self.manager.task_group.create_task(self.file(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        soup = link_container = date = None  # type: ignore
        src_selector = "src"
        if is_stream_redirect(scrape_item.url):
            soup, scrape_item.url = await self.client.get_soup_and_return_url(self.domain, scrape_item.url)

        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)
        if await self.check_complete_from_referer(scrape_item):
            return

        if not soup:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        # try video
        if not self.manager.config_manager.deep_scrape:
            link_container = soup.select_one("video > source")

        # try image
        if not (link_container or self.manager.config_manager.deep_scrape):
            link_container = soup.select_one(IMAGE_PREVIEW_SELECTOR)

        # fallback for everything else
        if not link_container:
            link_container = soup.select_one(DOWNLOAD_BUTTON_SELECTOR)
            src_selector = "href"

        link_str: str = link_container.get(src_selector) if link_container else None  # type: ignore
        if not link_str:
            raise ScrapeError(422, "Couldn't find source", origin=scrape_item)

        link = self.parse_url(link_str)
        if not scrape_item.possible_datetime:
            date_str = soup.select_one(ITEM_DATE_SELECTOR)
            if date_str:
                date = parse_datetime(date_str.text.strip())

            scrape_item.possible_datetime = date

        title: str = soup.select_one("h1").text  # type: ignore
        await self.handle_direct_link(scrape_item, link, fallback_filename=title)

    async def handle_direct_link(
        self, scrape_item: ScrapeItem, url: URL | None = None, fallback_filename: str | None = None
    ) -> None:
        """Handles direct links (CDNs URLs) before sending them to the downloader.

        If `link` is not supplied, `scrape_item.url` will be used by default

        `fallback_filename` will only be used if the link has not `n` query parameter"""

        link = url or scrape_item.url
        referer = ""

        if is_reinforced_link(link):
            referer = link
            link: URL = await self.handle_reinforced_link(scrape_item, link)
            if not link:
                return

        else:
            link = override_cdn(link)

        try:
            src_filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            src_filename, ext = self.get_filename_and_ext(scrape_item.url.name, assume_ext=".mp4")

        filename, _ = self.get_filename_and_ext(link.query.get("n") or fallback_filename)  # type: ignore
        if not url:
            referer = referer or URL("https://get.bunkrr.su/")
            scrape_item.url = referer
        await self.handle_file(link, scrape_item, src_filename, ext, custom_filename=filename)

    @error_handling_wrapper
    async def handle_reinforced_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> URL:
        """Gets the download link for a given reinforced URL (get.bunkr.su)."""
        url = url or scrape_item.url
        file_id_index = url.parts.index("file") + 1
        file_id = url.parts[file_id_index]
        data = json.dumps({"id": file_id})
        headers = {
            "Referer": str(url),
            "Content-Type": "application/json",
            "Origin": "https://get.bunkrr.su",
        }
        async with self.request_limiter:
            json_resp: dict = await self.client.post_data(self.domain, API_ENTRYPOINT, data=data, headers_inc=headers)

        api_response = ApiResponse(**json_resp)
        link_str = decrypt_api_response(api_response)
        return self.parse_url(link_str)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_final_url(self, scrape_item: ScrapeItem) -> URL:
        if not is_reinforced_link(scrape_item.url):
            return scrape_item.url
        return await self.handle_reinforced_link(scrape_item, scrape_item.url)


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
    if "brg-bk.cdn" in url.host:
        return url.with_host("i-burger.bunkr.ru")
    return url


def is_reinforced_link(url: URL) -> bool:
    assert url.host
    return any(part in url.host.split(".") for part in ("get",))


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%H:%M:%S %d/%m/%Y")
    return calendar.timegm(parsed_date.timetuple())


def decrypt_api_response(api_response: ApiResponse) -> str:
    if not api_response.encrypted:
        return api_response.url

    time_key = math.floor(api_response.timestamp / 0xE10)
    secret_key = f"SECRET_KEY_{time_key}"
    byte_array = decode_base64_to_byte_array(api_response.url)
    return xor_decrypt(byte_array, secret_key)


def decode_base64_to_byte_array(url_base64_encrypted: str) -> bytearray:
    binary_data = base64.b64decode(url_base64_encrypted)
    byte_array = bytearray(binary_data)
    return byte_array


def xor_decrypt(data: bytearray, key: str) -> str:
    key_bytes = key.encode("utf-8")
    decrypted_data = bytearray(len(data))
    for i in range(len(data)):
        decrypted_data[i] = data[i] ^ key_bytes[i % len(key_bytes)]  # XOR over each byte

    return decrypted_data.decode("utf-8", errors="ignore")
