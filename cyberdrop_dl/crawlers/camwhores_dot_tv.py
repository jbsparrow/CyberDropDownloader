from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._kvs import KernelVideoSharingCrawler, Video
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils.utilities import get_og_properties

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


PRIMARY_URL = AbsoluteHttpURL("https://www.camwhores.tv")


class CamwhoresTVCrawler(KernelVideoSharingCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "camwhores.tv"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # Returns 404 without the trailing slash
        if scrape_item.url.name:
            scrape_item.url = scrape_item.url / ""
        await super().fetch(scrape_item)

    def get_video_info(self, soup: BeautifulSoup) -> Video:
        video = super().get_video_info(soup)
        return video._replace(title=get_og_properties(soup).title)

    def parse_url(self, link_str: str, relative_to: AbsoluteHttpURL | None = None, *_) -> AbsoluteHttpURL:
        return super().parse_url(link_str, relative_to, trim=False)
