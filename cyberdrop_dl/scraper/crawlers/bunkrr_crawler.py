from __future__ import annotations

import calendar
import contextlib
import datetime
import re
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError, NoExtensionError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
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


class BunkrrCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"bunkrr": ["bunkrr", "bunkr"]}
    primary_base_domain = URL("https://bunkr.site")

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "Bunkrr")
        self.request_limiter = AsyncLimiter(10, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if scrape_item.url.host.startswith("get"):
            scrape_item.url = await self.reinforced_link(scrape_item.url)
            if not scrape_item.url:
                return

        if "a" in scrape_item.url.parts:
            await self.album(scrape_item)
        elif self.is_cdn(scrape_item.url):
            await self.handle_direct_link(scrape_item)
        else:
            await self.file(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)
        album_id = scrape_item.url.parts[2]
        scrape_item.album_id = album_id
        results = await self.get_album_results(album_id)
        scrape_item.type = FILE_HOST_ALBUM
        scrape_item.children = scrape_item.children_limit = 0

        with contextlib.suppress(IndexError, TypeError):
            scrape_item.children_limit = (
                self.manager.config_manager.settings_data.download_options.maximum_number_of_children[scrape_item.type]
            )

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = soup.select_one("title").text.rsplit(" | Bunkr")[0].strip()
        title = self.create_title(title, scrape_item.url.parts[2], None)
        scrape_item.add_to_parent_title(title)

        card_listings: list[Tag] = soup.select('div[class*="relative group/item theItem"]')
        for card_listing in card_listings:
            filename = card_listing.select_one('p[class*="theName"]').text
            file_ext = "." + filename.split(".")[-1]
            thumbnail = card_listing.select_one("img").get("src")
            date_str = card_listing.select_one('span[class*="theDate"]').text.strip()
            date = self.parse_datetime(date_str)
            link = card_listing.find("a").get("href")
            if link.startswith("/"):
                link = URL("https://" + scrape_item.url.host + link)

            link = URL(link)
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                part_of_album=True,
                album_id=album_id,
                possible_datetime=date,
                add_parent=scrape_item.url,
            )

            valid_extensions = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"]
            src = thumbnail.replace("/thumbs/", "/")
            src = URL(src, encoded=True)
            src = src.with_suffix(file_ext).with_query(None)
            if file_ext.lower() not in FILE_FORMATS["Images"]:
                src = src.with_host(src.host.replace("i-", ""))

            src = self.override_cdn(src)
            # Scrape new URL if unable to get final URL from thumbnail
            if file_ext.lower() not in valid_extensions or "no-image" in src.name:
                self.manager.task_group.create_task(self.run(new_scrape_item))

            else:
                src_filename, ext = get_filename_and_ext(src.name)
                if not self.check_album_results(src, results):
                    await self.handle_file(src, new_scrape_item, src_filename, ext, custom_filename=filename)

            scrape_item.children += 1
            if scrape_item.children_limit and scrape_item.children >= scrape_item.children_limit:
                raise MaxChildrenError(origin=scrape_item)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path)
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        """
        Some old page details may have the uuid as the title instead of the filename.
        Commenting out this code ensures we always get the actual filename from `get.bunkr.su`, at the expense of one additional request


        # try video
        link_container = soup.select_one("video > source")
        src_selector = "src"

        # try image
        if not link_container:
            link_container = soup.select_one("img.max-h-full.w-auto.object-cover.relative")

        # fallback for everything else
        if not link_container:
        """
        link_container = soup.select_one("a.btn.ic-download-01")
        src_selector = "href"

        link = link_container.get(src_selector) if link_container else None

        if not link:
            raise ScrapeError(404, f"Could not find source for: {scrape_item.url}", origin=scrape_item)

        link = URL(link)
        await self.handle_direct_link(scrape_item, link, fallback_filename=soup.select_one("h1").text)

    async def handle_direct_link(
        self, scrape_item: ScrapeItem, url: URL | None = None, fallback_filename: str | None = None
    ) -> None:
        """Handles direct links (CDNs URLs) before sending them to the downloader.

        If `link` is not supplied, `scrape_item.url` will be used by default

        `fallback_filename` will only be used if the link has not `n` query parameter"""
        link = url or scrape_item.url
        if "get" in link.host:
            link: URL = await self.reinforced_link(link)
            if not link:
                return
        try:
            src_filename, ext = get_filename_and_ext(link.name)
        except NoExtensionError:
            src_filename, ext = get_filename_and_ext(scrape_item.url.name)
        filename = link.query.get("n") or fallback_filename
        if not url:
            scrape_item = self.create_scrape_item(scrape_item, URL("https://get.bunkrr.su/"), "")
        await self.handle_file(link, scrape_item, src_filename, ext, custom_filename=filename)

    @error_handling_wrapper
    async def reinforced_link(self, url: URL) -> URL:
        """Gets the download link for a given reinforced URL."""
        """get.bunkr.su"""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, url)

        try:
            link_container = soup.select('a[download*=""]')[-1]
        except IndexError:
            link_container = soup.select("a[class*=download]")[-1]
        return URL(link_container.get("href"))

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def is_cdn(url: URL) -> bool:
        """Checks if a given URL is from a CDN."""
        return bool(CDN_POSSIBILITIES.match(url.host))

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%H:%M:%S %d/%m/%Y")
        return calendar.timegm(date.timetuple())

    @staticmethod
    def override_cdn(link: URL) -> URL:
        new_link = link
        if "milkshake" in link.host:
            new_link = link.with_host("mlk-bk.cdn.gigachad-cdn.ru")
        return new_link
