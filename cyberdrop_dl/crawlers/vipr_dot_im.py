from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


IMG_SELECTOR = "div#body a > img"


class ViprImCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {"Image": "/...", "Thumbnail": "/th/..."}
    primary_base_domain = AbsoluteHttpURL("https://vipr.im")
    DOMAIN = "vipr.im"
    FOLDER_DOMAIN = "Vipr.im"

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

        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, IMG_SELECTOR, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)

    async def thumbnail(self, scrape_item: ScrapeItem) -> None:
        scrape_item.url = self.get_canonical_url(scrape_item.url)
        self.manager.task_group.create_task(self.run(scrape_item))

    def get_canonical_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return self.primary_base_domain / get_image_id(url)


def get_image_id(url: URL) -> str:
    return Path(url.name).stem
