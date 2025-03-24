from __future__ import annotations

import calendar
import datetime
import enum
import re
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup, Tag
from yarl import URL

from cyberdrop_dl.clients.errors import PasswordProtectedError, ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

CDN_PATTERNS = {
    "jpg5.su": r"^(?:https?:\/\/?)((jpg.church\/images)|(simp..jpg.church)|(jpg.fish\/images)|(simp..jpg.fish)|(jpg.fishing\/images)|(simp..jpg.fishing)|(simp..host.church)|(simp..jpg..su))(\/.*)",
    "imagepond.net": r"^(?:https?:\/\/)?(media.imagepond.net\/.*)",
    "img.kiwi": r"^(?:https?:\/\/)?img\.kiwi\/images\/.*",
}

CDN_POSSIBILITIES = re.compile("|".join(CDN_PATTERNS.values()))
JS_SELECTOR = "script[data-cfasync='false']:contains('image_viewer_full_fix')"
JS_CONTENT_START = "document.addEventListener('DOMContentLoaded', function(event)"
ITEM_DESCRIPTION_SELECTOR = "p[class*=description-meta]"


class UrlType(enum.StrEnum):
    album = enum.auto()
    image = enum.auto()
    video = enum.auto()


class CheveretoCrawler(Crawler):
    JPG5_DOMAINS: ClassVar[list[str]] = [
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
        self.next_page_selector = "a[data-pagination=next]"
        self.album_title_selector = "a[data-text=album-name]"
        self.album_img_selector = "a[class='image-container --media'] img"
        self.profile_item_selector = "a[class='image-container --media']"
        self.profile_title_selector = 'meta[property="og:title"]'
        self.images_parts = "image", "img"
        self.album_parts = "a", "album"
        self.video_parts = "video", "videos"
        self.direct_link_parts = ("images",)
        if site == "jpg5.su":
            self.request_limiter = AsyncLimiter(1, 5)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if is_direct_link(scrape_item.url):
            return await self.handle_direct_link(scrape_item)
        scrape_item.url = scrape_item.url.with_host(self.primary_base_domain.host)  # type: ignore
        if any(part in scrape_item.url.parts for part in self.album_parts):
            await self.album(scrape_item)
        elif any(part in scrape_item.url.parts for part in self.images_parts):
            await self.image(scrape_item)
        elif any(part in scrape_item.url.parts for part in self.video_parts):
            await self.video(scrape_item)
        elif any(part in scrape_item.url.parts for part in self.direct_link_parts):
            filename, ext = get_filename_and_ext(scrape_item.url.name)
            await self.handle_file(scrape_item.url, scrape_item, filename, ext)
        else:
            await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title_tag = soup.select_one(self.profile_title_selector)
        title_text: str = title_tag.get("content")  # type: ignore
        title = self.create_title(title_text)
        scrape_item.setup_as_profile(title)

        async for soup in self.web_pager(scrape_item):
            for album in self.iter_children(scrape_item, soup.select(self.profile_item_selector)):
                self.manager.task_group.create_task(self.run(album))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id, canonical_url = self.get_canonical_url(scrape_item)
        results = await self.get_album_results(album_id)
        password = scrape_item.url.query.get("password", "")
        scrape_item.url = scrape_item.url.with_query(None)

        async with self.request_limiter:
            sub_albums = scrape_item.url / "sub"
            soup: BeautifulSoup = await self.client.get_soup(self.domain, sub_albums)

        scrape_item.url = canonical_url

        if "This content is password protected" in soup.text and password:
            password_data = {"content-password": password}
            async with self.request_limiter:
                soup = BeautifulSoup(
                    await self.client.post_data(self.domain, scrape_item.url, data=password_data, raw=True),
                    "html.parser",
                )

        if "This content is password protected" in soup.text:
            raise PasswordProtectedError(message="Wrong password" if password else None)

        title_tag = soup.select_one(self.album_title_selector)
        title_text: str = title_tag.get_text()  # type: ignore
        title = self.create_title(title_text, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        async for soup in self.web_pager(scrape_item):
            for image in self.iter_children(scrape_item, soup.select(self.album_img_selector), "src"):
                if not self.check_album_results(image.url, results):
                    await self.handle_direct_link(image)

        async for soup in self.web_pager(scrape_item, sub_albums=True):
            for sub_album in self.iter_children(scrape_item, soup.select(self.profile_item_selector)):
                self.manager.task_group.create_task(self.run(sub_album))

    def iter_children(self, scrape_item: ScrapeItem, children: Sequence[Tag], selector: str = "href"):
        for item in children:
            link_str: str = item.get(selector)  # type: ignore
            link = self.parse_url(link_str)
            new_scrape_item = scrape_item.create_child(link)
            scrape_item.add_children()
            yield new_scrape_item

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

        if self.domain == "jpg5.su":
            filename, link = await self.get_embed_info(scrape_item.url)
        else:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

            try:
                link_str: str = soup.select_one(selector[0]).get(selector[1])  # type: ignore
                link = self.parse_url(link_str)
                name = link.name.replace(".md.", ".").replace(".th.", ".")
                link = link.with_name(name)
                filename = link.name

            except AttributeError:
                raise ScrapeError(422, f"Couldn't find {url_type.value} source") from None

        scrape_item.url = canonical_url
        desc_rows = soup.select(ITEM_DESCRIPTION_SELECTOR)
        date_str: str | None = None
        for row in desc_rows:
            if any(text in row.text.casefold() for text in ("uploaded", "added to")):
                date_str = row.select_one("span").get("title")  # type: ignore
                break

        if date_str:
            date = parse_datetime(date_str)
            scrape_item.possible_datetime = date

        filename, ext = get_filename_and_ext(filename)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        """Handles a direct link."""
        scrape_item.url = scrape_item.url.with_name(scrape_item.url.name.replace(".md.", ".").replace(".th.", "."))
        pattern = r"(jpg\.fish/)|(jpg\.fishing/)|(jpg\.church/)"
        scrape_item.url = self.parse_url(re.sub(pattern, r"host.church/", str(scrape_item.url)))
        filename, ext = get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)

    async def get_embed_info(self, url: URL) -> tuple[str, URL]:
        embed_url = self.primary_base_domain / "oembed" / ""
        embed_url = embed_url.with_query(url=str(url), format="json")

        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, embed_url)

        link_str: str = json_resp["url"]
        link_str = link_str.replace(".md.", ".").replace(".th.", ".")
        link = self.parse_url(link_str)
        filename = json_resp["title"] + link.suffix

        return filename, link

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
        new_path = "/" + "/".join(new_parts)
        return _id, self.parse_url(new_path, scrape_item.url.with_path("/"))

    async def web_pager(self, scrape_item: ScrapeItem, sub_albums: bool = False) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        url = scrape_item.url if not sub_albums else scrape_item.url / "sub"
        page_url = get_sort_by_new_url(url)
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url, origin=scrape_item)
            next_page = soup.select_one(self.next_page_selector)
            yield soup
            page_url_str: str = next_page.get("href") if next_page else None  # type: ignore
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str, trim=False)


def get_sort_by_new_url(url: URL) -> URL:
    return url.with_query({"sort": "date_desc", "page": 1})


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
    return calendar.timegm(parsed_date.timetuple())


def is_direct_link(url: URL) -> bool:
    """Determines if the url is a direct link or not."""
    return bool(CDN_POSSIBILITIES.match(str(url)))
