from __future__ import annotations

import calendar
import datetime
import enum
import re
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import PasswordProtectedError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

CDN_PATTERNS = {
    "jpg.church": r"^(?:https?:\/\/?)((jpg.church\/images)|(simp..jpg.church)|(jpg.fish\/images)|(simp..jpg.fish)|(jpg.fishing\/images)|(simp..jpg.fishing)|(simp..host.church)|(simp..jpg..su))(\/.*)",
    "imagepond.net": r"^(?:https?:\/\/)?(media.imagepond.net\/.*)",
    "img.kiwi": r"^(?:https?:\/\/)?img\.kiwi\/images\/.*",
}

CDN_POSSIBILITIES = re.compile("|".join(CDN_PATTERNS.values()))


class UrlType(enum.StrEnum):
    album = enum.auto()
    image = enum.auto()
    video = enum.auto()


class CheveretoCrawler(Crawler):
    JPG5_DOMAINS: ClassVar[tuple[str, ...]] = [
        "jpg5.su",
        "jpg.homes",
        "jpg.church",
        "jpg.fish",
        "jpg.fishing",
        "jpg.pet",
        "jpeg.pet",
        "jpg1.su",
        "jpg2.su",
        "jpg3.su",
        "jpg4.su",
        "host.church",
    ]

    PRIMARY_BASE_DOMAINS: ClassVar[dict[str, URL]] = {
        "jpg5.su": URL("https://jpg5.su"),
        "imagepond.net": URL("https://imagepond.net"),
        "img.kiwi": URL("https://img.kiwi"),
    }

    FOLDER_DOMAINS: ClassVar[dict[str, str]] = {
        "jpg5.su": "JPG5",
        "imagepond.net": "ImagePond",
        "img.kiwi": "ImgKiwi",
    }

    SUPPORTED_SITES: ClassVar[dict[str, list]] = {
        "jpg5.su": JPG5_DOMAINS,
        "imagepond.net": ["imagepond.net"],
        "img.kiwi": ["img.kiwi"],
    }

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, self.FOLDER_DOMAINS.get(site, "Chevereto"))
        self.primary_base_domain = self.PRIMARY_BASE_DOMAINS.get(site, URL(f"https://{site}"))
        self.request_limiter = AsyncLimiter(10, 1)
        self.next_page_selector = "a[data-pagination=next]"
        self.album_title_selector = "a[data-text=album-name]"
        self.album_img_selector = "a[class='image-container --media'] img"
        self.profile_item_selector = "a[class='image-container --media']"
        self.profile_title_selector = 'meta[property="og:title"]'
        self.images_parts = "image", "img", "images"
        self.album_parts = "a", "album"
        self.video_parts = "video", "videos"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if self.check_direct_link(scrape_item.url):
            await self.handle_direct_link(scrape_item)
            return
        scrape_item.url = scrape_item.url.with_host(self.primary_base_domain.host)
        if any(part in scrape_item.url.parts for part in self.album_parts):
            await self.album(scrape_item)
        elif any(part in scrape_item.url.parts for part in self.images_parts):
            await self.image(scrape_item)
        elif any(part in scrape_item.url.parts for part in self.video_parts):
            await self.video(scrape_item)
        else:
            await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(soup.select_one(self.profile_title_selector).get("content"), None, None)

        async for soup in self.web_pager(scrape_item):
            links = soup.select(self.profile_item_selector)
            for link in links:
                link = link.get("href")
                if not link:
                    continue
                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]
                link = URL(link)
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    new_title_part=title,
                    part_of_album=True,
                    add_parent=scrape_item.url,
                )
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id, canonical_url = self.get_canonical_url(scrape_item)
        results = await self.get_album_results(album_id)
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True
        password = scrape_item.url.query.get("password", "")
        scrape_item.url = scrape_item.url.with_query(None)

        async with self.request_limiter:
            sub_albums_soup: BeautifulSoup = await self.client.get_soup(
                self.domain, scrape_item.url / "sub", origin=scrape_item
            )

        scrape_item.url = canonical_url

        if "This content is password protected" in sub_albums_soup.text and password:
            password_data = {"content-password": password}
            async with self.request_limiter:
                sub_albums_soup = BeautifulSoup(
                    await self.client.post_data(
                        self.domain,
                        scrape_item.url,
                        data=password_data,
                        raw=True,
                        origin=scrape_item,
                    ),
                    "html.parser",
                )

        if "This content is password protected" in sub_albums_soup.text:
            raise PasswordProtectedError(message="Wrong password" if password else None, origin=scrape_item)

        title = self.create_title(
            sub_albums_soup.select_one(self.album_title_selector).get_text(),
            album_id,
            None,
        )

        sub_albums = sub_albums_soup.select(self.profile_item_selector)
        for album in sub_albums:
            sub_album_link = album.get("href")
            if sub_album_link.startswith("/"):
                sub_album_link = self.primary_base_domain / sub_album_link[1:]

            sub_album_link = URL(sub_album_link)
            new_scrape_item = self.create_scrape_item(scrape_item, sub_album_link, "", True)
            self.manager.task_group.create_task(self.run(new_scrape_item))

        async for soup in self.web_pager(scrape_item):
            links = soup.select(self.album_img_selector)
            for link in links:
                link = link.get("src")
                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]
                link = URL(link)
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    new_title_part=title,
                    part_of_album=True,
                    album_id=album_id,
                    add_parent=scrape_item.url,
                )
                if not self.check_album_results(link, results):
                    await self.handle_direct_link(new_scrape_item)

    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        url_type = UrlType.video
        selector = "meta[property='og:video']", "content"
        await self._proccess_media_item(scrape_item, url_type, selector)

    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        url_type = UrlType.image
        selector = "div[id=image-viewer] img", "src"
        await self._proccess_media_item(scrape_item, url_type, selector)

    @error_handling_wrapper
    async def _proccess_media_item(self, scrape_item: ScrapeItem, url_type: UrlType, selector: tuple[str, str]) -> None:
        """Scrapes a media item."""
        if await self.check_complete_from_referer(scrape_item):
            return

        _, canonical_url = self.get_canonical_url(scrape_item, url_type=url_type)
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.url = canonical_url

        try:
            link = URL(soup.select_one(selector[0]).get(selector[1]))
            link = link.with_name(link.name.replace(".md.", ".").replace(".th.", "."))
        except AttributeError:
            raise ScrapeError(422, f"Couldn't find {url_type.value} source", origin=scrape_item) from None

        desc_rows = soup.select("p[class*=description-meta]")
        date = None
        for row in desc_rows:
            if "uploaded" in row.text.casefold():
                date = row.select_one("span").get("title")
                break

        if date:
            date = self.parse_datetime(date)
            scrape_item.possible_datetime = date

        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_name(scrape_item.url.name.replace(".md.", ".").replace(".th.", "."))
        pattern = r"(jpg\.fish/)|(jpg\.fishing/)|(jpg\.church/)"
        scrape_item.url = URL(re.sub(pattern, r"host.church/", str(scrape_item.url)))
        filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def get_canonical_url(self, scrape_item: ScrapeItem, url_type: UrlType = UrlType.album) -> tuple[str, URL]:
        "Returns the id and canonical URL from a given item (album, image or video)"
        if url_type not in UrlType:
            raise ValueError("Invalid URL Type")

        search_parts = self.album_parts
        if url_type == UrlType.image:
            search_parts = self.images_parts
        elif url_type == UrlType.video:
            search_parts = self.video_parts

        found_part = next(part for part in search_parts if part in scrape_item.url.parts)
        name_index = scrape_item.url.parts.index(found_part) + 1
        name = scrape_item.url.parts[name_index]
        _id = name.rsplit(".")[-1]
        new_parts = scrape_item.url.parts[1:name_index] + (_id,)
        return _id, scrape_item.url.with_path("/".join(new_parts))

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = await self.get_sort_by_new_url(scrape_item.url)
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(self.next_page_selector)
            yield soup
            if next_page:
                page_url = next_page.get("href")
                if page_url:
                    if page_url.startswith("/"):
                        page_url = self.primary_base_domain / page_url[1:]
                    page_url = URL(page_url)
                    continue
            break

    @staticmethod
    async def get_sort_by_new_url(url: URL) -> URL:
        return url.with_query({"sort": "date_desc", "page": 1})

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(date.timetuple())

    @staticmethod
    def check_direct_link(url: URL) -> bool:
        """Determines if the url is a direct link or not."""
        return bool(CDN_POSSIBILITIES.match(str(url)))
