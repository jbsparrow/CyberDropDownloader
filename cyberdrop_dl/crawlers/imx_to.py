from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


IMG_SELECTOR = "div#container a > img"


class ImxToCrawler(Crawler):
    primary_base_domain = URL("https://imx.to")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imx.to", "Imx.to")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        cookies = {"continue": 1}
        self.update_cookies(cookies)

    @create_task_id
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
            soup = await self.client.post_data_get_soup(self.domain, scrape_item.url, data=data)

        link_str: str = soup.select_one(IMG_SELECTOR)["src"]  # type: ignore
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def thumbnail(self, scrape_item: ScrapeItem) -> None:
        link = self.thumbnail_to_img(scrape_item.url)
        scrape_item.url = self.get_canonical_url(link)
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".jpg")
        await self.handle_file(link, scrape_item, filename, ext)

    def thumbnail_to_img(self, url: URL) -> URL:
        path = url.path.split("/t/")[-1]
        return self.primary_base_domain / "u/i" / path

    def get_canonical_url(self, url: URL) -> URL:
        return self.primary_base_domain / get_image_id(url)


def get_image_id(url: URL) -> str:
    return Path(url.name).stem
