from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

IMAGE_SELECTOR = "img[id*=main-image]"
VIDEO_SELECTOR = "video > source"
ALBUM_ITEM_SELECTOR = "a[class*=spotlight]"


class HotPicCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"hotpic": ["hotpic", "2385290.xyz"]}
    primary_base_domain = URL("https://hotpic.cc")
    update_unsupported = True

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "HotPic")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        elif "i" in scrape_item.url.parts:
            return await self.file(scrape_item)
        elif any(p in scrape_item.url.parts for p in ("uploads", "reddit")):
            return await self.handle_direct_link(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        album_id = scrape_item.url.parts[2]
        title = self.create_title(soup.title.text.rsplit(" - ")[0], scrape_item.album_id)  # type: ignore
        scrape_item.setup_as_profile(title, album_id=album_id)

        for _, link in self.iter_tags(soup, ALBUM_ITEM_SELECTOR):
            await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        file = soup.select_one(VIDEO_SELECTOR) or soup.select_one(IMAGE_SELECTOR)
        if not file:
            raise ScrapeError(422)
        link_str: str = file.get("src")  # type: ignore
        link = self.parse_url(link_str)
        await self.handle_direct_link(scrape_item, link)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        link = thumbnail_to_img(scrape_item.url)
        canonical_url = get_canonical_url(link)
        filename, ext = self.get_filename_and_ext(canonical_url.name)
        await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)


def thumbnail_to_img(url: URL) -> URL:
    if "thumb" not in url.parts:
        return url
    if (new_ext := ".mp4") != url.suffix:
        new_ext = ".jpg"
    url = with_suffix_encoded(url, new_ext)
    new_parts = [p for p in url.parts if p not in ("/", "thumb")]
    new_path = "/".join(new_parts)
    return url.with_path(new_path)


def with_suffix_encoded(url: URL, suffix: str) -> URL:
    name = Path(url.raw_name).with_suffix(suffix)
    return url.parent.joinpath(str(name), encoded=True).with_query(url.query).with_fragment(url.fragment)


def get_canonical_url(url: URL) -> URL:
    return url.with_host("hotpic.cc")
