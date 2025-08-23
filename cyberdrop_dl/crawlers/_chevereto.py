from __future__ import annotations

import base64
import itertools
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import PasswordProtectedError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


class Selector:
    ITEM_DESCRIPTION = "p[class*=description-meta]"
    ITEM = "a[class='image-container --media']"
    NEXT_PAGE = "a[data-pagination=next]"

    DATE_SINGLE_ITEM = f"{ITEM_DESCRIPTION}:contains('Uploaded') span"
    DATE_ALBUM_ITEM = f"{ITEM_DESCRIPTION}:contains('Added to') span"
    DATE = css.CssAttributeSelector(f"{DATE_SINGLE_ITEM}, {DATE_ALBUM_ITEM}", "title")
    MAIN_IMAGE = css.CssAttributeSelector("div#image-viewer img", "src")


_DECRYPTION_KEY = b"seltilovessimpcity@simpcityhatesscrapers"


class CheveretoCrawler(Crawler, is_generic=True):
    SUPPORTED_PATHS: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "Album": (
            "/a/<id>",
            "/a/<name>.<id>",
            "/album/<id>",
            "/album/<name>.<id>",
        ),
        "Image": (
            "/img/<id>",
            "/img/<name>.<id>",
            "/image/<id>",
            "/image/<name>.<id>",
        ),
        "Profiles": "/<user_name>",
        "Video": (
            "/video/<id>",
            "/video/<name>.<id>",
            "/videos/<id>",
            "/videos/<name>.<id>",
        ),
        "Direct links": "",
    }
    NEXT_PAGE_SELECTOR = Selector.NEXT_PAGE
    CHEVERETO_SUPPORTS_VIDEO = True

    def __init_subclass__(cls, **kwargs) -> None:
        if not cls.CHEVERETO_SUPPORTS_VIDEO:
            cls.SUPPORTED_PATHS = paths = cls.SUPPORTED_PATHS.copy()  # type: ignore[reportIncompatibleVariableOverride]
            _ = paths.pop("Video", None)
        super().__init_subclass__(**kwargs)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if self.is_subdomain(scrape_item.url):
            return await self.direct_file(scrape_item)

        match scrape_item.url.parts[1:]:
            case ["a" | "album", album_slug]:
                return await self.album(scrape_item, _id(album_slug))
            case ["img" | "image" | "video" | "videos", _]:
                return await self.media(scrape_item)
            case ["images", _, *_]:
                return await self.direct_file(scrape_item)
            case [_]:
                return await self.profile(scrape_item)
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL):
        url = super().transform_url(url)
        match url.parts[1:]:
            case ["a" | "album" as part, album_slug, "sub"]:
                return url.with_path(f"{part}/{album_slug}", keep_query=True)
            case ["img" | "image" | "video" | "videos" as part, slug]:
                return url.with_path(f"{part}/{_id(slug)}", keep_query=True)
            case _:
                return url

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(_sort_by_new(scrape_item.url), trim=False):
            if not title:
                title = self.create_title(open_graph.title(soup))
                scrape_item.setup_as_profile(title)
            self._process_page(scrape_item, soup)

    async def _get_redirect_url(self, url: AbsoluteHttpURL):
        async with self.request_limiter:
            head = await self.client.get_head(self.DOMAIN, url)
        if location := head.get("location"):
            return self.parse_url(location, url.origin(), trim=False)
        return url

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        results = await self.get_album_results(album_id)
        title: str = ""

        # We need the full URL (aka "/<name>.<id>") to fetch sub albums
        if "." not in scrape_item.url.name:
            scrape_item.url = await self._get_redirect_url(scrape_item.url)

        # The first redirect may have only added a trailing slash, try again
        if not scrape_item.url.name and "." not in scrape_item.url.parts[-2]:
            scrape_item.url = await self._get_redirect_url(scrape_item.url)

        async for soup in self.web_pager(_sort_by_new(scrape_item.url), trim=False):
            if not title:
                if _is_password_protected(soup):
                    await self._unlock_password_protected_album(scrape_item)
                    return await self.album(scrape_item, album_id)

                title = self.create_title(open_graph.title(soup), album_id)
                scrape_item.setup_as_album(title, album_id=album_id)
            self._process_page(scrape_item, soup, results)

        sub_album_url = scrape_item.url / "sub"
        async for soup in self.web_pager(_sort_by_new(sub_album_url), trim=False):
            for _, sub_album in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(sub_album))

    def _process_page(
        self, scrape_item: ScrapeItem, soup: BeautifulSoup, results: dict[str, int] | None = None
    ) -> None:
        for thumb, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
            assert thumb
            source = _thumbnail_to_src(thumb)
            if results and self.check_album_results(source, results):
                continue

            # for images, we can download the file from the thumbnail, skipping an additional request per img
            # cons: we won't get the upload date
            if image_url := _match_img(new_scrape_item.url):
                new_scrape_item.url = image_url
                self.create_task(self.direct_file(new_scrape_item, source))
                continue

            self.create_task(self.run(new_scrape_item))

    async def _unlock_password_protected_album(self, scrape_item: ScrapeItem) -> None:
        password = scrape_item.pop_query("password")
        if not password:
            raise PasswordProtectedError

        async with self.request_limiter:
            soup = await self.client.post_data_get_soup(
                self.DOMAIN, _sort_by_new(scrape_item.url / ""), data={"content-password": password}
            )
        if _is_password_protected(soup):
            raise PasswordProtectedError(message="Wrong password")

    @error_handling_wrapper
    async def direct_file(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None, assume_ext: str | None = None
    ) -> None:
        link = _thumbnail_to_src(url or scrape_item.url)
        await super().direct_file(scrape_item, link, assume_ext)

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str = open_graph.get("video", soup) or open_graph.get("image", soup)
        if not link_str or "loading.svg" in link_str:
            link_str = Selector.MAIN_IMAGE(soup)

        source = self.parse_url(link_str)
        scrape_item.possible_datetime = self.parse_iso_date(Selector.DATE(soup))
        await self.direct_file(scrape_item, source)

    def parse_url(
        self, link_str: str, relative_to: AbsoluteHttpURL | None = None, *, trim: bool | None = None
    ) -> AbsoluteHttpURL:
        if not link_str.startswith("https") and not link_str.startswith("/"):
            link_str = _xor_decrypt(link_str, _DECRYPTION_KEY)
        return super().parse_url(link_str, relative_to, trim=trim)


def _is_password_protected(soup: BeautifulSoup) -> bool:
    return "This content is password protected" in soup.text


def _id(slug: str) -> str:
    return slug.rsplit(".")[-1]


def _match_img(url: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
    match url.parts[1:]:
        case ["img" | "image" as part, image_slug, *_]:
            return url.origin() / part / _id(image_slug)


def _thumbnail_to_src(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    new_name = url.name
    for trash in (".md.", ".th.", ".fr."):
        new_name = new_name.replace(trash, ".")
    return url.with_name(new_name)


def _sort_by_new(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    init_page = int(url.query.get("page") or 1)
    return url.with_query(sort="date_desc", page=init_page)


def _xor_decrypt(encrypted_str: str, key: bytes) -> str:
    encrypted_data = bytes.fromhex(base64.b64decode(encrypted_str).decode())
    decrypted_data = bytearray(b_input ^ b_key for b_input, b_key in zip(encrypted_data, itertools.cycle(key)))
    return decrypted_data.decode("utf-8", errors="ignore")
