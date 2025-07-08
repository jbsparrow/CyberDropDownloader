from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.leakedzone import LeakedZoneCrawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


LIGHT_GALLERY_ITEM_SELECTOR = "div.light-gallery-item"
PRIMARY_URL = AbsoluteHttpURL("https://hotleak.vip")
IMAGES_CDN = AbsoluteHttpURL("https://image-cdn.hotleak.vip")


class HotLeakVipCrawler(LeakedZoneCrawler):
    DOMAIN: ClassVar[str] = "hotleak.vip"
    FOLDER_DOMAIN: ClassVar[str] = "HotLeakVip"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    IMAGES_CDN: ClassVar[AbsoluteHttpURL] = IMAGES_CDN

    @classmethod
    def get_encoded_video_url(cls, soup: BeautifulSoup) -> str:
        video_info_text = css.select_one_get_attr(soup, LIGHT_GALLERY_ITEM_SELECTOR, "data-video")
        video_data: dict[str, Any] = json.loads(video_info_text)
        return video_data["source"][0]["src"]
