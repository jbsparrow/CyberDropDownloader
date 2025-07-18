from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, with_suffix_encoded

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    IMAGE = "img[id*=main-image]"
    VIDEO = "video > source"
    ALBUM_ITEM = "a[class*=spotlight]"
    IMAGE_OR_VIDEO = f"{IMAGE}, {VIDEO}"


PRIMARY_URL = AbsoluteHttpURL("https://hotpic.cc")
_SELECTORS = Selectors()


class HotPicCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/album/...",
        "Image": "/i/...",
    }
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "hotpic", "2385290.xyz"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    UPDATE_UNSUPPORTED: ClassVar[bool] = True
    DOMAIN: ClassVar[str] = "hotpic"
    FOLDER_DOMAIN: ClassVar[str] = "HotPic"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        elif "i" in scrape_item.url.parts:
            return await self.file(scrape_item)
        elif any(p in scrape_item.url.parts for p in ("uploads", "reddit")):
            return await self.handle_direct_link(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        album_id = scrape_item.url.parts[2]
        title = self.create_title(css.select_one_get_text(soup, "title").rsplit(" - ")[0], scrape_item.album_id)
        scrape_item.setup_as_profile(title, album_id=album_id)

        for _, link in self.iter_tags(soup, _SELECTORS.ALBUM_ITEM):
            await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str = css.select_one_get_attr(soup, _SELECTORS.IMAGE_OR_VIDEO, "src")
        link = self.parse_url(link_str)
        await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem, link: AbsoluteHttpURL | None = None) -> None:
        link = thumbnail_to_img(link or scrape_item.url)
        canonical_url = link.with_host("hotpic.cc")
        filename, ext = self.get_filename_and_ext(canonical_url.name)
        await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)


def thumbnail_to_img(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    if "thumb" not in url.parts:
        return url
    if (new_ext := ".mp4") != url.suffix:
        new_ext = ".jpg"
    url = with_suffix_encoded(url, new_ext)
    new_parts = [p for p in url.parts if p not in ("/", "thumb")]
    new_path = "/".join(new_parts)
    return url.with_path(new_path)
