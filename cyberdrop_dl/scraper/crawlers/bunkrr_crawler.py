from __future__ import annotations

import calendar
import datetime
import re
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable

    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.managers.manager import Manager

BASE_CDNS = [
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
    r"mlk-bk\.cdn\.gigachad-cdn",
]

EXTENDED_CDNS = [f"cdn-{cdn}" for cdn in BASE_CDNS]
IMAGE_CDNS = [f"i-{cdn}" for cdn in BASE_CDNS]
CDNS = BASE_CDNS + EXTENDED_CDNS + IMAGE_CDNS
CDN_REGEX_STR = r"^(?:(?:(" + "|".join(CDNS) + r")[0-9]{0,2}(?:redir)?))\.bunkr?\.[a-z]{2,3}$"
CDN_POSSIBILITIES = re.compile(CDN_REGEX_STR)


album_item_selector = "div[class*='relative group/item theItem']"
item_name_selector = "p[class*='theName']"
item_date_selector = 'span[class*="theDate"]'

valid_extensions = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"]


@dataclass(frozen=True)
class AlbumItem:
    name: str
    thumbnail: str
    date: int
    url: URL

    @classmethod
    def from_tag(cls, tag: Tag, parse_url: Callable[..., URL]) -> AlbumItem:
        name = tag.select_one(item_name_selector).text  # type: ignore
        thumbnail: str = tag.select_one("img").get("src")  # type: ignore
        date_str = tag.select_one(item_date_selector).text.strip()  # type: ignore
        date = parse_datetime(date_str)
        link_str: str = tag.find("a").get("href")  # type: ignore
        link = parse_url(link_str)
        return cls(name, thumbnail, date, link)

    def get_src(self, parse_url: Callable[..., URL]) -> URL:
        src_str = self.thumbnail.replace("/thumbs/", "/")
        src = parse_url(src_str)
        src = src.with_suffix(self.suffix).with_query(None)
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
        self.album_item_selector = "div[class*='relative group/item theItem']"
        self.item_name_selector = "p[class*='theName']"
        self.item_date_selector = 'span[class*="theDate"]'

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
            await self.handle_direct_link(scrape_item)
        else:
            await self.file(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        album_id = scrape_item.url.parts[2]
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        title = soup.select_one("title").text.rsplit(" | Bunkr")[0].strip()  # type: ignore
        title = self.create_title(title, album_id)
        scrape_item.add_to_parent_title(title)
        results = await self.get_album_results(album_id)

        item_tags: list[Tag] = soup.select(self.album_item_selector)
        parse_url = partial(self.parse_url, relative_to=scrape_item.url.with_path("/"))
        create = partial(self.create_scrape_item, scrape_item, add_parent=scrape_item.url)

        for item_tag in item_tags:
            item = AlbumItem.from_tag(item_tag, parse_url)
            new_scrape_item = create(item.url, possible_datetime=item.date)
            src = item.get_src(self.parse_url)

            # Scrape new URL if unable to get final URL from thumbnail
            if src.suffix.lower() not in valid_extensions or "no-image" in src.name or self.deep_scrape(src):
                self.manager.task_group.create_task(self.run(new_scrape_item))

            else:
                src_filename, ext = self.get_filename_and_ext(src.name, assume_ext=".mp4")
                filename, _ = self.get_filename_and_ext(item.name, assume_ext=".mp4")
                if not self.check_album_results(src, results):
                    await self.handle_file(src, new_scrape_item, src_filename, ext, custom_filename=filename)

            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        if not scrape_item.url:
            return
        soup = link_container = None
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
            link_container = soup.select_one("img.max-h-full.w-auto.object-cover.relative")

        # fallback for everything else
        if not link_container:
            link_container = soup.select_one("a.btn.ic-download-01")
            src_selector = "href"

        link_str: str = link_container.get(src_selector) if link_container else None
        if not link_str:
            raise ScrapeError(422, "Couldn't find source", origin=scrape_item)

        link = self.parse_url(link_str)
        date = None
        date_str = soup.select_one('span[class*="theDate"]')
        if date_str:
            date = parse_datetime(date_str.text.strip())

        new_scrape_item = self.create_scrape_item(scrape_item, scrape_item.url, possible_datetime=date)
        await self.handle_direct_link(new_scrape_item, link, fallback_filename=soup.select_one("h1").text)

    async def handle_direct_link(
        self, scrape_item: ScrapeItem, url: URL | None = None, fallback_filename: str | None = None
    ) -> None:
        """Handles direct links (CDNs URLs) before sending them to the downloader.

        If `link` is not supplied, `scrape_item.url` will be used by default

        `fallback_filename` will only be used if the link has not `n` query parameter"""

        link = url or scrape_item.url
        if is_reinforced_link(link):
            link: URL = await self.handle_reinforced_link(link, scrape_item)

        if not link:
            return
        try:
            src_filename, ext = self.get_filename_and_ext(link.name)
        except NoExtensionError:
            src_filename, ext = self.get_filename_and_ext(scrape_item.url.name, assume_ext=".mp4")
        filename = link.query.get("n") or fallback_filename
        if not url:
            scrape_item = self.create_scrape_item(scrape_item, URL("https://get.bunkrr.su/"))
        await self.handle_file(link, scrape_item, src_filename, ext, custom_filename=filename)

    @error_handling_wrapper
    async def handle_reinforced_link(self, url: URL, scrape_item: ScrapeItem) -> URL | None:
        """Gets the download link for a given reinforced URL (get.bunkr.su)."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, url, origin=scrape_item)

        try:
            link_container = soup.select('a[download*=""]')[-1]
        except IndexError:
            link_container = soup.select("a[class*=download]")[-1]
        link_str: str = link_container.get("href")  # type: ignore
        return self.parse_url(link_str)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def deep_scrape(self, url: URL) -> bool:
        assert url.host
        return any(part in url.host.split(".") for part in ("burger",)) or self.manager.config_manager.deep_scrape

    async def get_final_url(self, scrape_item: ScrapeItem) -> URL:
        if not is_reinforced_link(scrape_item.url):
            return scrape_item.url
        return await self.handle_reinforced_link(scrape_item.url, scrape_item)


def is_stream_redirect(url: URL) -> bool:
    assert url.host
    return any(part in url.host for part in ("cdn12", "cdn-")) or url.host == "cdn.bunkr.ru"


def is_cdn(url: URL) -> bool:
    """Checks if a given URL is from a CDN."""
    assert url.host
    return bool(CDN_POSSIBILITIES.match(url.host))


def override_cdn(url: URL) -> URL:
    assert url.host
    if "milkshake" not in url.host:
        return url.with_host("mlk-bk.cdn.gigachad-cdn.ru")
    return url


def is_reinforced_link(url: URL) -> bool:
    assert url.host
    return any(part in url.host.split(".") for part in ("get",))


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%H:%M:%S %d/%m/%Y")
    return calendar.timegm(parsed_date.timetuple())
