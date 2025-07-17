from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.imx_to import ImxToCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://acidimg.cc")


class AcidImgCrawler(ImxToCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Image": "/i/...",
        "Thumbnail": "/upload/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "acidimg.cc"
    FOLDER_DOMAIN: ClassVar[str] = "AcidImg"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "i" in scrape_item.url.parts:
            return await self.image(scrape_item)
        if "upload" in scrape_item.url.parts:
            return await self.thumbnail(scrape_item)
        raise ValueError

    def thumbnail_to_img(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        index = url.parts.index("upload") + 2
        path = "/".join(url.parts[index:])
        return PRIMARY_URL / "upload/big" / path

    def get_canonical_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        image_id = get_image_id(url)
        return PRIMARY_URL / f"img-{image_id}.html"


def get_image_id(url: AbsoluteHttpURL) -> str:
    return url.name.removesuffix(".html").removeprefix("img-")
