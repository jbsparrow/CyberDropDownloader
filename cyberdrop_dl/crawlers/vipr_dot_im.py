from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://vipr.im")
IMG_SELECTOR = "div#body a > img"


class ViprImCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Image": "/...", "Thumbnail": "/th/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "vipr.im"
    FOLDER_DOMAIN: ClassVar[str] = "Vipr.im"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "th" in scrape_item.url.parts:
            return await self.thumbnail(scrape_item)
        if len(scrape_item.url.parts) == 2:
            return await self.image(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, IMG_SELECTOR, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)

    async def thumbnail(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = self.get_canonical_url(scrape_item.url)
        self.create_task(self.run(scrape_item))

    def get_canonical_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return PRIMARY_URL / get_image_id(url)


def get_image_id(url: AbsoluteHttpURL) -> str:
    return Path(url.name).stem
