from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


IMG_SELECTOR = "div#container a > img"
PRIMARY_URL = AbsoluteHttpURL("https://imx.to")


class ImxToCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Image": "/i/...", "Thumbnail": "/t/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imx.to"

    async def async_startup(self) -> None:
        cookies = {"continue": 1}
        self.update_cookies(cookies)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "i" in scrape_item.url.parts:
            return await self.image(scrape_item)
        if "t" in scrape_item.url.parts:
            return await self.thumbnail(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        data = {"imgContinue": "Continue+to+image+...+"}
        async with self.request_limiter:
            soup = await self.client.post_data_get_soup(self.DOMAIN, scrape_item.url, data=data)

        link_str: str = css.select_one_get_attr(soup, IMG_SELECTOR, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def thumbnail(self, scrape_item: ScrapeItem) -> None:
        link = self.thumbnail_to_img(scrape_item.url)
        scrape_item.url = self.get_canonical_url(link)
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)

    def thumbnail_to_img(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        path = url.path.split("/t/")[-1]
        return PRIMARY_URL / "u/i" / path

    def get_canonical_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return PRIMARY_URL / get_image_id(url)


def get_image_id(url: AbsoluteHttpURL) -> str:
    return Path(url.name).stem
