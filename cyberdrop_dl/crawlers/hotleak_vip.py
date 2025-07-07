from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyberdrop_dl.crawlers.leakedzone import LeakedZoneCrawler, decode_video_url
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.m3u8 import M3U8Media
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    LIGHT_GALLERY_ITEM = "div.light-gallery-item"
    MODEL_NAME = "div.actor-name > h1"


_SELECTORS = Selectors()


class HotLeakVipCrawler(LeakedZoneCrawler):
    DOMAIN = "hotleak.vip"
    FOLDER_DOMAIN = "HotLeakVip"
    PRIMARY_URL = AbsoluteHttpURL("https://hotleak.vip")

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        light_gallery_item = soup.select_one(_SELECTORS.LIGHT_GALLERY_ITEM)
        if not light_gallery_item:
            raise ScrapeError(422)

        video_data = json.loads(light_gallery_item["data-video"])
        url: AbsoluteHttpURL = self.parse_url(decode_video_url(video_data["source"][0]["src"]))
        m3u8_media = M3U8Media(await self._get_m3u8(url))
        model_name = soup.select_one(_SELECTORS.MODEL_NAME).get_text(strip=True)

        filename, ext = self.get_filename_and_ext(f"{model_name} [{video_id}].mp4")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8_media=m3u8_media)

    async def handle_gallery_image(self, scrape_item, post):
        image_url: AbsoluteHttpURL = self.parse_url(post["player"])
        filename, ext = self.get_filename_and_ext(image_url.name)
        new_scrape_item = scrape_item.create_child(image_url)
        await self.handle_file(new_scrape_item.url, new_scrape_item, filename, ext)
