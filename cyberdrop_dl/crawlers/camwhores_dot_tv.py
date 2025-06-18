from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._kvs import KernelVideoSharingCrawler, Video
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import get_og_properties

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


PRIMARY_URL = AbsoluteHttpURL("https://www.camwhores.tv")


class CamwhoresTVCrawler(KernelVideoSharingCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "camwhores.tv"

    def get_video_info(self, soup: BeautifulSoup) -> Video:
        video = super().get_video_info(soup)
        return video._replace(title=get_og_properties(soup).title)
