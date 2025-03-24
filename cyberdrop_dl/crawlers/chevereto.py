from __future__ import annotations

import calendar
import datetime
import re
from typing import TYPE_CHECKING, ClassVar, Literal

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import PasswordProtectedError, ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

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


UrlType = Literal["album", "image", "video"]


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
        self.item_selector = "a[class='image-container --media']"
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
            return await self.album(scrape_item)
        if any(part in scrape_item.url.parts for part in self.images_parts):
            return await self.image(scrape_item)
        if any(part in scrape_item.url.parts for part in self.video_parts):
            return await self.video(scrape_item)
        if any(part in scrape_item.url.parts for part in self.direct_link_parts):
            return await self.handle_direct_link(scrape_item)

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

        async for soup in self.web_pager(scrape_item.url):
            for src, item in self.iter_children(scrape_item, soup):
                # Item may be an image, a video or an album
                # For images, we can download the file from the thumbnail
                if any(p in item.url.parts for p in self.images_parts):
                    _, item.url = self.get_canonical_url(item, url_type="image")
                    await self.handle_direct_link(item, src)
                    return
                # For videos and albums, we have to keep scraping
                self.manager.task_group.create_task(self.run(item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id, canonical_url = self.get_canonical_url(scrape_item)
        results = await self.get_album_results(album_id)
        password = scrape_item.url.query.get("password", "")
        scrape_item.url = scrape_item.url.with_query(None)
        original_url = scrape_item.url

        async with self.request_limiter:
            sub_albums = scrape_item.url / "sub"
            soup: BeautifulSoup = await self.client.get_soup(self.domain, sub_albums)

        scrape_item.url = canonical_url

        if "This content is password protected" in soup.text and password:
            data = {"content-password": password}
            async with self.request_limiter:
                html = await self.client.post_data(self.domain, scrape_item.url, data=data, raw=True)
                soup = BeautifulSoup(html, "html.parser")

        if "This content is password protected" in soup.text:
            raise PasswordProtectedError(message="Wrong password" if password else None)

        title_tag = soup.select_one(self.album_title_selector)
        title_text: str = title_tag.get_text()  # type: ignore
        title = self.create_title(title_text, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        async for soup in self.web_pager(scrape_item.url):
            for image_src, image in self.iter_children(scrape_item, soup):
                if not self.check_album_results(image_src, results):
                    _, image.url = self.get_canonical_url(image, url_type="image")
                    await self.handle_direct_link(image, image_src)

        # Sub album URL needs to be the full URL + a 'sub'
        # Using the canonical URL + 'sub' won't work because it redirects to the "homepage" of the album
        sub_album_url = original_url / "sub"
        async for soup in self.web_pager(sub_album_url):
            for _, sub_album in self.iter_children(scrape_item, soup):
                self.manager.task_group.create_task(self.run(sub_album))

    def iter_children(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> Generator[tuple[URL, ScrapeItem]]:
        """Generates tuple with an URL from the `src` value and a new scrape item from the `href` value`"""
        for item in soup.select(self.item_selector):
            src_str, link_str = item.select_one("img")["src"], item["href"]  # type: ignore
            src, link = self.parse_url(src_str), self.parse_url(link_str)  # type: ignore
            new_scrape_item = scrape_item.create_child(link)
            scrape_item.add_children()
            yield src, new_scrape_item

    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        selector = "meta[property='og:video']", "content"
        await self._proccess_media_item(scrape_item, "video", selector)

    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        selector = "div[id=image-viewer] img", "src"
        await self._proccess_media_item(scrape_item, "image", selector)

    @error_handling_wrapper
    async def _proccess_media_item(self, scrape_item: ScrapeItem, url_type: UrlType, selector: tuple[str, str]) -> None:
        """Scrapes a media item."""
        if await self.check_complete_from_referer(scrape_item):
            return

        _, canonical_url = self.get_canonical_url(scrape_item, url_type=url_type)
        if await self.check_complete_from_referer(canonical_url):
            return

        if self.domain == "jpg5.su":
            _, link = await self.get_embed_info(scrape_item.url)
        else:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

            try:
                link_str: str = soup.select_one(selector[0]).get(selector[1])  # type: ignore
                link = self.parse_url(link_str)

            except AttributeError:
                raise ScrapeError(422, f"Couldn't find {url_type} source") from None

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

        await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        """Handles a direct link."""
        link = url or scrape_item.url
        link = link.with_name(link.name.replace(".md.", ".").replace(".th.", "."))
        pattern = r"(jpg\.fish/)|(jpg\.fishing/)|(jpg\.church/)"
        link = self.parse_url(re.sub(pattern, r"host.church/", str(link)))
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

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

    def get_canonical_url(self, scrape_item: ScrapeItem, url_type: UrlType = "album") -> tuple[str, URL]:
        "Returns the id and canonical URL from a given item (album, image or video)"

        search_parts = self.album_parts
        if url_type == "image":
            search_parts = self.images_parts
        elif url_type == "video":
            search_parts = self.video_parts

        found_part = next(part for part in search_parts if part in scrape_item.url.parts)
        name_index = scrape_item.url.parts.index(found_part) + 1
        name = scrape_item.url.parts[name_index]
        _id = name.rsplit(".")[-1]
        new_parts = scrape_item.url.parts[1:name_index] + (_id,)
        new_path = "/" + "/".join(new_parts)
        return _id, self.parse_url(new_path, scrape_item.url.with_path("/"))

    async def web_pager(self, url: URL) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = get_sort_by_new_url(url)
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
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
