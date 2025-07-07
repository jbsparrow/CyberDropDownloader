from __future__ import annotations

import binascii
import itertools
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
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
    MODEL_NAME_COLLECTION = "div.actor-name > h1"
    MODEL_NAME = "h2.actor-title-port"


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
        return await self.collection(scrape_item)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        model_name: str = soup.select_one(_SELECTORS.MODEL_NAME_COLLECTION).get_text(strip=True)
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
        video_id: str = str(post["id"])
        canonical_url: AbsoluteHttpURL = PRIMARY_URL / scrape_item.url.parts[1] / "video" / video_id
        if await self.check_complete_from_referer(canonical_url):
            return
        scrape_item.url = canonical_url
        url: AbsoluteHttpURL = self.parse_url(decode_video_url(post["stream_url_play"]))
        m3u8_media = M3U8Media(await self._get_m3u8(url))
        filename, ext = self.get_filename_and_ext(f"{model_name} [{video_id}].mp4")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8_media=m3u8_media)

    async def handle_gallery_image(self, scrape_item: ScrapeItem, post: dict[str, Any]) -> None:
        image_url: AbsoluteHttpURL = IMAGES_CDN / post["image"]
        filename, ext = self.get_filename_and_ext(image_url.name)
        new_scrape_item = scrape_item.create_child(image_url)
        await self.handle_file(new_scrape_item.url, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        player = soup.select_one(_SELECTORS.JS_PLAYER)
        if not player:
            raise ScrapeError(422)

        url: AbsoluteHttpURL = decode_video_url(get_encoded_video_url(player.text))
        m3u8_media = M3U8Media(await self._get_m3u8(url))
        model_name = soup.select_one(_SELECTORS.MODEL_NAME).get_text(strip=True)

        filename, ext = self.get_filename_and_ext(f"{model_name} [{video_id}].mp4")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8_media=m3u8_media)


def get_encoded_video_url(script_text: str) -> str:
    return get_text_between(script_text, 'file: f("', '"),')


def decode_video_url(url: str) -> str:
    # cut first and last 16 characters, reverse, base64 decode
    # TODO: Research if this work on any JW Player
    return binascii.a2b_base64(url[-17:15:-1]).decode()
