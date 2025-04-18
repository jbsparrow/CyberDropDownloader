from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, TypeAlias

from bs4 import BeautifulSoup

from cyberdrop_dl.clients.errors import PasswordProtectedError, ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


JPG5_REPLACE_HOST_REGEX = re.compile(r"(jpg\.fish/)|(jpg\.fishing/)|(jpg\.church/)")

JS_SELECTOR = "script[data-cfasync='false']:contains('image_viewer_full_fix')"
JS_CONTENT_START = "document.addEventListener('DOMContentLoaded', function(event)"
ITEM_DESCRIPTION_SELECTOR = "p[class*=description-meta]"
ALBUM_TITLE_SELECTOR = "a[data-text=album-name]"
ITEM_SELECTOR = "a[class='image-container --media']"
PROFILE_TITLE_SELECTOR = 'meta[property="og:title"]'
IMAGES_PARTS = "image", "img"
ALBUM_PARTS = "a", "album"
VIDEO_PARTS = "video", "videos"
DIRECT_LINK_PARTS = ("images",)


def _clean(url: URL) -> URL:
    return url.with_name(url.name.replace(".md.", ".").replace(".th.", "."))


def _sort_by_new(url: URL) -> URL:
    return url.with_query(sort="date_desc", page=1)


UrlType: TypeAlias = Literal["album", "image", "video"]


class CheveretoCrawler(Crawler):
    next_page_selector = "a[data-pagination=next]"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        return await self._fetch_chevereto_defaults(scrape_item)

    async def _fetch_chevereto_defaults(self, scrape_item: ScrapeItem):
        if scrape_item.url.host.count(".") > 1:  # type: ignore
            return await self.handle_direct_link(scrape_item)
        if any(part in scrape_item.url.parts for part in ALBUM_PARTS):
            return await self.album(scrape_item)
        if any(part in scrape_item.url.parts for part in IMAGES_PARTS):
            return await self.image(scrape_item)
        if any(part in scrape_item.url.parts for part in VIDEO_PARTS):
            return await self.video(scrape_item)
        if any(part in scrape_item.url.parts for part in DIRECT_LINK_PARTS):
            return await self.handle_direct_link(scrape_item)
        await self.profile(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an user profile."""
        title: str = ""
        async for soup in self.web_pager(_sort_by_new(scrape_item.url), trim=False):
            if not title:
                title: str = soup.select_one(PROFILE_TITLE_SELECTOR)["content"]  # type: ignore
                title = self.create_title(title)
                scrape_item.setup_as_profile(title)

            for thumb, new_scrape_item in self.iter_children(scrape_item, soup, ITEM_SELECTOR):
                # Item may be an image, a video or an album
                # For images, we can download the file from the thumbnail
                if any(p in new_scrape_item.url.parts for p in IMAGES_PARTS):
                    _, new_scrape_item.url = self.get_canonical_url(new_scrape_item, "image")
                    await self.handle_direct_link(new_scrape_item, thumb)
                    continue
                # For videos and albums, we have to keep scraping
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        album_id, canonical_url = self.get_canonical_url(scrape_item)
        results = await self.get_album_results(album_id)
        original_url = scrape_item.url
        title: str = ""
        async for soup in self.web_pager(_sort_by_new(scrape_item.url), trim=False):
            if not title:
                await self.check_password_protected(soup, scrape_item.url)
                title: str = soup.select_one(ALBUM_TITLE_SELECTOR).text  # type: ignore
                title = self.create_title(title, album_id)
                scrape_item.setup_as_album(title, album_id=album_id)
                scrape_item.url = canonical_url

            for thumb, new_scrape_item in self.iter_children(scrape_item, soup, ITEM_SELECTOR):
                assert thumb
                if self.check_album_results(thumb, results):
                    continue
                _, new_scrape_item.url = self.get_canonical_url(new_scrape_item, "image")
                await self.handle_direct_link(new_scrape_item, thumb)

        # Sub album URL needs to be the full URL + a 'sub'
        # Using the canonical URL + 'sub' won't work because it redirects to the "homepage" of the album
        sub_album_url = original_url / "sub"
        async for soup in self.web_pager(_sort_by_new(sub_album_url), trim=False):
            for _, sub_album in self.iter_children(scrape_item, soup, ITEM_SELECTOR):
                self.manager.task_group.create_task(self.run(sub_album))

    async def check_password_protected(self, soup: BeautifulSoup, url: URL) -> None:
        password = url.query.get("password", "")
        url = url.with_query(None)

        if "This content is password protected" in soup.text and password:
            data = {"content-password": password}
            async with self.request_limiter:
                html = await self.client.post_data(self.domain, url, data=data, raw=True)
                soup = BeautifulSoup(html, "html.parser")

        if "This content is password protected" in soup.text:
            raise PasswordProtectedError(message="Wrong password" if password else None)

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

        _, canonical_url = self.get_canonical_url(scrape_item, url_type)
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        try:
            link_str: str = soup.select_one(selector[0])[selector[1]]  # type: ignore
            link = self.parse_url(link_str)

        except AttributeError:
            raise ScrapeError(422, f"Couldn't find {url_type} source") from None

        scrape_item.possible_datetime = self.parse_date(get_date_from_soup(soup))
        scrape_item.url = canonical_url
        await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, url: URL | None = None) -> None:
        """Handles a direct link."""
        link = _clean(url or scrape_item.url)
        link = self.parse_url(re.sub(JPG5_REPLACE_HOST_REGEX, r"host.church/", str(link)))
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    async def get_embed_info(self, url: URL) -> tuple[str, URL]:
        embed_url = self.primary_base_domain / "oembed" / ""
        embed_url = embed_url.with_query(url=str(url), format="json")
        async with self.request_limiter:
            json_resp: dict[str, str] = await self.client.get_json(self.domain, embed_url)

        link = _clean(self.parse_url(json_resp["url"]))
        filename = json_resp["title"] + link.suffix
        return filename, link

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def get_canonical_url(self, scrape_item: ScrapeItem, url_type: UrlType = "album") -> tuple[str, URL]:
        """Returns the id and canonical URL from a given item (album, image or video)."""
        search_parts = ALBUM_PARTS
        if url_type == "image":
            search_parts = IMAGES_PARTS
        elif url_type == "video":
            search_parts = VIDEO_PARTS

        found_part = next(p for p in search_parts if p in scrape_item.url.parts)
        name_index = scrape_item.url.parts.index(found_part) + 1
        name = scrape_item.url.parts[name_index]
        _id = name.rsplit(".")[-1]
        new_parts = scrape_item.url.parts[1:name_index] + (_id,)
        new_path = "/" + "/".join(new_parts)
        return _id, self.parse_url(new_path, scrape_item.url.origin())


def get_date_from_soup(soup: BeautifulSoup) -> str:
    for row in soup.select(ITEM_DESCRIPTION_SELECTOR):
        if any(text in row.text.casefold() for text in ("uploaded", "added to")):
            return row.select_one("span")["title"]  # type: ignore
    return ""
