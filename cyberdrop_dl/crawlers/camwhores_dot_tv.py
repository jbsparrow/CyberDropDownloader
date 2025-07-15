from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._kvs import KernelVideoSharingCrawler, Video
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils import open_graph

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.crawlers.crawler import SupportedPaths


PRIMARY_URL = AbsoluteHttpURL("https://www.camwhores.tv")


class CamwhoresTVCrawler(KernelVideoSharingCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Search": "/search/...",
        "Categories": "/categories/...",
        "Tags": "/tags/...",
        "Videos": "/videos/...",
        "Members": "/members/<member_id>",
    }

    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "camwhores.tv"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # Returns 404 without the trailing slash
        if scrape_item.url.name:
            scrape_item.url = scrape_item.url / ""
        await super().fetch(scrape_item)

    def get_video_info(self, soup: BeautifulSoup) -> Video:
        video = super().get_video_info(soup)
        return video._replace(title=open_graph.title(soup))

    def parse_url(self, link_str: str, relative_to: AbsoluteHttpURL | None = None, *_) -> AbsoluteHttpURL:
        return super().parse_url(link_str, relative_to, trim=False)

    async def picture(self, scrape_item: ScrapeItem) -> None:
        # images are encrypted, similar to the video URLS
        # https://www.camwhores.tv/get_image/93/9da0742b1fb753388286b95c2a66d766/sources/100000/100557/1472879.jpg/
        # TODO: Find out license to decrypt them
        # Almost all albums are private anyways..
        raise NotImplementedError

    async def album(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError
