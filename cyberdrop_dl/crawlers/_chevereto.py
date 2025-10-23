from __future__ import annotations

import base64
from typing import TYPE_CHECKING, ClassVar, final

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, copy_signature
from cyberdrop_dl.exceptions import PasswordProtectedError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper, xor_decrypt

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


class Selector:
    ITEM_DESCRIPTION = "p[class*=description-meta]"
    ITEM = "a.image-container"
    NEXT_PAGE = "a[data-pagination=next]"

    DATE_SINGLE_ITEM = f"{ITEM_DESCRIPTION}:-soup-contains('Uploaded') span"
    DATE_ALBUM_ITEM = f"{ITEM_DESCRIPTION}:-soup-contains('Added to') span"
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
        "Category": "/category/<name>",
        "Image": (
            "/img/<id>",
            "/img/<name>.<id>",
            "/image/<id>",
            "/image/<name>.<id>",
        ),
        "Profile": "/<user_name>",
        "Video": (
            "/video/<id>",
            "/video/<name>.<id>",
            "/videos/<id>",
            "/videos/<name>.<id>",
        ),
        "Direct links": "",
    }
    NEXT_PAGE_SELECTOR = Selector.NEXT_PAGE
    DEFAULT_TRIM_URLS: ClassVar[bool] = False
    CHEVERETO_SUPPORTS_VIDEO: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs) -> None:
        if not cls.CHEVERETO_SUPPORTS_VIDEO:
            cls.SUPPORTED_PATHS = paths = cls.SUPPORTED_PATHS.copy()  # type: ignore[reportIncompatibleVariableOverride]
            _ = paths.pop("Video", None)
        super().__init_subclass__(**kwargs)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if self.is_subdomain(scrape_item.url):
            return await self.direct_file(scrape_item)

        match scrape_item.url.parts[1:]:
            case ["a" | "album" | "category", album_slug]:
                return await self.album(scrape_item, _id(album_slug))
            case ["img" | "image" | "video" | "videos", _]:
                return await self.media(scrape_item)
            case ["images", _, *_]:
                return await self.direct_file(scrape_item)
            case [_, "albums"]:
                return await self.profile(scrape_item)
            case [_]:
                return await self.profile(scrape_item)
            case _:
                raise ValueError

    @final
    @staticmethod
    def _thumbnail_to_src(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        new_name = url.name
        for trash in (".md.", ".th.", ".fr."):
            new_name = new_name.replace(trash, ".")
        return url.with_name(new_name)

    @classmethod
    def _match_img(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        match url.parts[1:]:
            case ["img" | "image" as part, image_slug, *_]:
                return url.origin() / part / _id(image_slug)

    @copy_signature(Crawler.request_soup)
    async def request_soup(self, url: AbsoluteHttpURL, *args, impersonate: bool = False, **kwargs) -> BeautifulSoup:
        # chevereto redirects are URL encoded and aiohttp always reencodes them by default, leading to an infinite redirect loop, so we use cURL
        # We may be able to use aiohttp in v4
        # See: https://github.com/jbsparrow/CyberDropDownloader/pull/1356#issuecomment-3349190328
        return await super().request_soup(url, *args, impersonate=True, **kwargs)

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
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

    async def _get_final_album_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if "category" in url.parts:
            return url

        # We need the full URL (aka "/<name>.<id>") to fetch sub albums
        if "." not in url.name:
            url = await self._get_redirect_url(url)

        # The first redirect may have only added a trailing slash, try again
        if not url.name and "." not in url.parts[-2]:
            url = await self._get_redirect_url(url)

        return url

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        results = await self.get_album_results(album_id)
        title: str = ""

        scrape_item.url = await self._get_final_album_url(scrape_item.url)

        async for soup in self.web_pager(_sort_by_new(scrape_item.url), trim=False):
            if not title:
                if _is_password_protected(soup):
                    await self._unlock_password_protected_album(scrape_item)
                    return await self.album(scrape_item, album_id)

                title = open_graph.get_title(soup) or open_graph.get("description", soup) or ""
                assert title
                title = self.create_title(title, album_id)
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
            if image_url := self._match_img(new_scrape_item.url):
                new_scrape_item.url = image_url

                if thumb:
                    # for images, we can download the file from the thumbnail, skipping an additional request per img
                    # cons: we won't get the upload date
                    source = self._thumbnail_to_src(thumb)
                    if results and self.check_album_results(source, results):
                        continue

                    self.create_task(self.direct_file(new_scrape_item, source))
                    continue

            self.create_task(self.run(new_scrape_item))

    async def _unlock_password_protected_album(self, scrape_item: ScrapeItem) -> None:
        password = scrape_item.pop_query("password")
        if not password:
            raise PasswordProtectedError

        soup = await self.request_soup(
            _sort_by_new(scrape_item.url / ""),
            method="POST",
            data={"content-password": password},
        )

        if _is_password_protected(soup):
            raise PasswordProtectedError(message="Wrong password")

    @error_handling_wrapper
    async def direct_file(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None, assume_ext: str | None = None
    ) -> None:
        link = self._thumbnail_to_src(url or scrape_item.url)
        await super().direct_file(scrape_item, link, assume_ext)

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
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
            encrypted_url = bytes.fromhex(base64.b64decode(link_str).decode())
            link_str = xor_decrypt(encrypted_url, _DECRYPTION_KEY)
        return super().parse_url(link_str, relative_to, trim=trim)


def _is_password_protected(soup: BeautifulSoup) -> bool:
    return "This content is password protected" in soup.text


def _id(slug: str) -> str:
    return slug.rsplit(".")[-1]


def _sort_by_new(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    init_page = int(url.query.get("page") or 1)
    if url.name:
        url = url / ""
    return url.with_query(sort="date_desc", page=init_page)
