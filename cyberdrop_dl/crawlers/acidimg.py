from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import create_task_id
from cyberdrop_dl.crawlers.imx_to import ImxToCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


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
        if "upload" in scrape_item.url.parts:
            return await self.thumbnail(scrape_item)
        raise ValueError

    def thumbnail_to_img(self, url: URL) -> URL:
        index = url.parts.index("upload") + 2
        path = "/".join(url.parts[index:])
        return self.primary_base_domain / "upload/big" / path

    def get_canonical_url(self, url: URL) -> URL:
        image_id = get_image_id(url)
        return self.primary_base_domain / f"img-{image_id}.html"


def get_image_id(url: URL) -> str:
    return url.name.removesuffix(".html").removeprefix("img-")
