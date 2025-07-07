from __future__ import annotations

import binascii
import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.compat import IntEnum
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.m3u8 import M3U8Media
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class PostType(IntEnum):
    IMAGE = 0
    VIDEO = 1


class Selectors:
    JS_PLAYER = "script:contains('playerInstance.setup')"
    MODEL_NAME_FROM_PROFILE = "div.actor-name > h1"
    MODEL_NAME_FROM_VIDEO = "h2.actor-title-port"
    MODEL_NAME = f"{MODEL_NAME_FROM_VIDEO}, {MODEL_NAME_FROM_PROFILE}"


_SELECTORS = Selectors()
PRIMARY_URL = AbsoluteHttpURL("https://leakedzone.com")
IMAGES_CDN = AbsoluteHttpURL("https://image-cdn.leakedzone.com/storage/")


class LeakedZoneCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/<model_id>/video/<video_id>",
        "Model": "/<model_id>",
    }
    DOMAIN: ClassVar[str] = "leakedzone"
    FOLDER_DOMAIN: ClassVar[str] = "LeakedZone"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    IMAGES_CDN: ClassVar[AbsoluteHttpURL] = IMAGES_CDN

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(3, 10)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if len(scrape_item.url.parts) >= 4 and "video" in scrape_item.url.parts:
            return await self.video(scrape_item, video_id=scrape_item.url.parts[-1])
        return await self.model(scrape_item)

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        model_name: str = css.select_one_get_text(soup, _SELECTORS.MODEL_NAME_FROM_PROFILE)
        title = self.create_title(model_name)
        scrape_item.setup_as_profile(title)

        headers = {"X-Requested-With": "XMLHttpRequest"}
        for page in itertools.count(1):
            async with self.request_limiter:
                posts = await self.client.get_json(self.DOMAIN, scrape_item.url.with_query(page=page), headers=headers)
            if not posts:
                break
            for post in posts:
                post_type = PostType(post["type"])
                if post_type == PostType.VIDEO:
                    await self.handle_gallery_video(scrape_item, post, model_name)
                elif post_type == PostType.IMAGE:
                    await self.handle_gallery_image(scrape_item, post)

    async def handle_gallery_video(self, scrape_item: ScrapeItem, post: dict[str, Any], model_name: str) -> None:
        video_id = str(post["id"])
        canonical_url = PRIMARY_URL / scrape_item.url.parts[1] / "video" / video_id
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url
        url = self.parse_url(_decode_video_url(post["stream_url_play"]))
        m3u8_media = M3U8Media(await self._get_m3u8(url))
        ext = ".mp4"
        filename = self.create_custom_filename(model_name, ext, file_id=video_id)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8_media=m3u8_media)

    async def handle_gallery_image(self, scrape_item: ScrapeItem, post: dict[str, Any]) -> None:
        image_url: AbsoluteHttpURL = self.IMAGES_CDN / post["image"].replace("_thumb", "")
        image_web_url = PRIMARY_URL / "photo" / str(post["id"])
        filename, ext = self.get_filename_and_ext(image_url.name)
        new_scrape_item = scrape_item.create_child(image_web_url)
        await self.handle_file(image_url, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        encoded_url = self.get_encoded_video_url(soup)
        url = self.parse_url(_decode_video_url(encoded_url))
        m3u8_media = M3U8Media(await self._get_m3u8(url))
        model_name = css.select_one_get_text(soup, _SELECTORS.MODEL_NAME)
        ext = ".mp4"
        filename = self.create_custom_filename(model_name, ext, file_id=video_id)
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8_media=m3u8_media)

    @classmethod
    def get_encoded_video_url(cls, soup: BeautifulSoup) -> str:
        js_text = css.select_one_get_text(soup, _SELECTORS.JS_PLAYER)
        return get_text_between(js_text, 'file: f("', '"),')


def _decode_video_url(url: str) -> str:
    # cut first and last 16 characters, reverse, base64 decode
    # TODO: Research if this work on any JW Player
    return binascii.a2b_base64(url[-17:15:-1]).decode()
