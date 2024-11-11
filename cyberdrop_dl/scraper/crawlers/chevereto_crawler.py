from __future__ import annotations

import calendar
import datetime
import re
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import PasswordProtectedError, ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem

CDN_PATTERNS = {
    "jpg.church": r"^(?:(jpg.church\/images\/...)|(simp..jpg.church)|(jpg.fish\/images\/...)|(simp..jpg.fish)|(jpg.fishing\/images\/...)|(simp..jpg.fishing)|(simp..host.church)|(simp..jpg..su))",
    "imagepond.net": r"(media.imagepond.net)",
    "img.kiwi": r"^(?:(img.kiwi\/images\/...))",
}

CDN_POSSIBILITIES = re.compile("|".join(CDN_PATTERNS.values()))


class CheveretoCrawler(Crawler):
    JPG_CHURCH_DOMAINS: ClassVar[tuple[str, ...]] = {
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
        "jpg5.su",
        "host.church",
    }

    PRIMARY_BASE_DOMAINS: ClassVar[dict[str, URL]] = {
        "imagepond.net": URL("https://imagepond.net"),
        "jpg.church": URL("https://jpg5.su"),
        "img.kiwi": URL("https://img.kiwi"),
    }

    FOLDER_DOMAINS: ClassVar[dict[str, str]] = {
        "imagepond.net": "ImagePond",
        "jpg.church": "JPGChurch",
        "img.kiwi": "ImgKiwi",
    }

    DOMAINS = PRIMARY_BASE_DOMAINS.keys() | JPG_CHURCH_DOMAINS

    def __init__(self, manager: Manager, domain: str) -> None:
        super().__init__(manager, domain, self.FOLDER_DOMAINS.get(domain, "Chevereto"))
        self.primary_base_domain = self.PRIMARY_BASE_DOMAINS.get(domain, URL(f"https://{domain}"))
        self.request_limiter = AsyncLimiter(10, 1)
        self.next_page_selector = "a[data-pagination=next]"
        self.album_title_selector = "a[data-text=album-name]"
        self.album_img_selector = "a[class='image-container --media'] img"
        self.profile_item_selector = "a[class='image-container --media']"
        self.profile_title_selector = 'meta[property="og:title"]'

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        if await self.check_direct_link(scrape_item.url):
            await self.handle_direct_link(scrape_item)
        else:
            scrape_item.url = self.primary_base_domain.with_path(scrape_item.url.path[1:]).with_query(
                scrape_item.url.query,
            )
            if "a" in scrape_item.url.parts or "album" in scrape_item.url.parts:
                await self.album(scrape_item)
            elif any(part in scrape_item.url.parts for part in ("image", "img", "images")):
                await self.image(scrape_item)
            else:
                await self.profile(scrape_item)

        self.scraping_progress.remove_task(task_id)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = self.create_title(soup.select_one(self.profile_title_selector).get("content"), None, None)

        async for soup in self.web_pager(scrape_item.url):
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
                    title,
                    True,
                    add_parent=scrape_item.url,
                )
                await self.handle_direct_link(new_scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id = scrape_item.url.parts[2]
        results = await self.get_album_results(album_id)
        scrape_item.album_id = album_id
        scrape_item.part_of_album = True
        password = scrape_item.url.query.get("password", "")
        scrape_item.url = scrape_item.url.with_query(None)

        async with self.request_limiter:
            sub_albums_soup: BeautifulSoup = await self.client.get_soup(
                self.domain,
                scrape_item.url / "sub",
                origin=scrape_item,
            )

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

        async for soup in self.web_pager(scrape_item.url):
            links = soup.select(self.album_img_selector)
            for link in links:
                link = link.get("src")
                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]
                link = URL(link)
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    link,
                    title,
                    True,
                    album_id,
                    add_parent=scrape_item.url,
                )
                if not await self.check_album_results(link, results):
                    await self.handle_direct_link(new_scrape_item)

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        try:
            link = URL(soup.select_one("div[id=image-viewer] img").get("src"))
            link = link.with_name(link.name.replace(".md.", ".").replace(".th.", "."))
        except AttributeError:
            raise ScrapeError(404, f"Could not find img source for {scrape_item.url}", origin=scrape_item) from None

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

    async def web_pager(self, url: URL) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = await self.get_sort_by_new_url(url)
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
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
    async def check_direct_link(url: URL) -> bool:
        """Determines if the url is a direct link or not."""
        return re.match(CDN_POSSIBILITIES, url.host)
