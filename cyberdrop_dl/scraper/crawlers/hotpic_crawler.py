from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class HotPicCrawler(Crawler):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {"hotpic": ["hotpic", "2385290.xyz"]}
    primary_base_domain = URL("https://hotpic.cc")

    def __init__(self, manager: Manager, site: str) -> None:
        super().__init__(manager, site, "HotPic")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        elif "i" in scrape_item.url.parts:
            return await self.image(scrape_item)
        elif any(p in scrape_item.url.parts for p in ("uploads", "reddit")):
            return await self.handle_direct_link(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        title = self.create_title(soup.title.text.rsplit(" - ")[0], scrape_item.album_id)  # type: ignore
        scrape_item.add_to_parent_title(title)
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        files = soup.select("a[class*=spotlight]")
        for file in files:
            link_str: str = file.get("href")  # type: ignore
            link = self.parse_url(link_str)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_str: str = soup.select_one("img[id*=main-image]").get("src")  # type: ignore
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def handle_direct_link(self, scrape_item: ScrapeItem) -> None:
        link = thumbnail_to_img(scrape_item.url)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)


def thumbnail_to_img(url: URL) -> URL:
    if "thumb" not in url.parts:
        return url

    url = with_suffix_encoded(url, ".jpg")
    new_parts = [p for p in url.parts if p not in ("/", "thumb")]
    new_path = "/".join(new_parts)
    return url.with_path(new_path)


def with_suffix_encoded(url: URL, suffix: str) -> URL:
    name = Path(url.raw_name).with_suffix(suffix)
    return url.parent.joinpath(str(name), encoded=True).with_query(url.query).with_fragment(url.fragment)
