from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


IMAGE_SELECTOR = "a[class=image]"
TITLE_SELECTOR = "h1#title"
PRIMARY_URL = AbsoluteHttpURL("https://xbunkr.com")


class XBunkrCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Albums": "/a/...", "Direct links": ""}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "xbunkr"
    FOLDER_DOMAIN: ClassVar[str] = "XBunkr"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "media" in scrape_item.url.host:
            await self.file(scrape_item)
        return await self.album(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        album_id = scrape_item.url.parts[2]
        title = self.create_title(css.select_one_get_text(soup, TITLE_SELECTOR), album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        for _, link in self.iter_tags(soup, IMAGE_SELECTOR):
            filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
            await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        filename, ext = self.get_filename_and_ext(scrape_item.url.name)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext)
