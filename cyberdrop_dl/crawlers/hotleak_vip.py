from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.leakedzone import LeakedZoneCrawler, decode_video_url
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.m3u8 import M3U8Media
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    LIGHT_GALLERY_ITEM = "div.light-gallery-item"
    MODEL_NAME = "div.actor-name > h1"


_SELECTORS = Selectors()
PRIMARY_URL = AbsoluteHttpURL("https://hotleak.vip")
IMAGES_CDN = AbsoluteHttpURL("https://image-cdn.hotleak.vip")


class HotLeakVipCrawler(LeakedZoneCrawler):
    DOMAIN: ClassVar[str] = "hotleak.vip"
    FOLDER_DOMAIN: ClassVar[str] = "HotLeakVip"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    IMAGES_CDN: ClassVar[AbsoluteHttpURL] = IMAGES_CDN

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        video_info_text = css.select_one_get_attr(soup, _SELECTORS.LIGHT_GALLERY_ITEM, "data-video")
        video_data: dict[str, Any] = json.loads(video_info_text)
        url = self.parse_url(decode_video_url(video_data["source"][0]["src"]))
        m3u8_media = M3U8Media(await self._get_m3u8(url))
        model_name = css.select_one_get_text(soup, _SELECTORS.MODEL_NAME)
        ext = ".mp4"
        filename = self.create_custom_filename(model_name, ext, file_id=video_id)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8_media=m3u8_media)
