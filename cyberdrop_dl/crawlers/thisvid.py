from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers._kvs import KernelVideoSharingCrawler, Video
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


PRIMARY_URL = AbsoluteHttpURL("https://thisvid.com")


class ThisVidCrawler(KernelVideoSharingCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "thisvid"
    FOLDER_DOMAIN: ClassVar[str] = "ThisVid"

    def get_video_info(self, soup: BeautifulSoup) -> Video:
        video = super().get_video_info(soup)
        title = css.select_one_get_text(soup, "title").split("- ThisVid.com")[0].strip()
        return video._replace(title=title)
