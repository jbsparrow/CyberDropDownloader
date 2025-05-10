from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.crawlers.imx_to import ImxToCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class AcidImgCrawler(ImxToCrawler):
    primary_base_domain = URL("https://acidimg.cc")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "acidimg.cc"
        self.folder_domain = "AcidImg"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "i" in scrape_item.url.parts:
            return await self.image(scrape_item)
        if "/upload/big/" in scrape_item.url.path:
            return await self.direct_file(scrape_item)
        if "/upload/small/" in scrape_item.url.path:
            return await self.thumbnail(scrape_item)
        raise ValueError

    def get_image_id(self, url: URL) -> str:
        return url.name.removesuffix(".html").removeprefix("img-")

    def thumbnail_to_img(self, url: URL) -> URL:
        path = url.path.split("/small/")[-1]
        return self.primary_base_domain / "upload/big" / path

    def get_canonical_url(self, url: URL) -> URL:
        image_id = self.get_image_id(url)
        return self.primary_base_domain / f"img-{image_id}.html"
