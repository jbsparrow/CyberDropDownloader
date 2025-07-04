from __future__ import annotations

import binascii
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.m3u8 import M3U8Media
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    JS_PLAYER = "script:contains('playerInstance.setup')"
    DATE_UPLOADED = "span.updated_at"
    MODEL_NAME = "h2.actor-title-port"


_SELECTORS = Selectors()

PRIMARY_URL = AbsoluteHttpURL("https://leakedzone.com")


class LeakedZoneCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/<model_id>/video/<video_id>",
        "Model": "/<model_id>",
    }
    DOMAIN: ClassVar[str] = "leakedzone"
    FOLDER_DOMAIN: ClassVar[str] = "LeakedZone"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(3, 10)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "video" in scrape_item.url.parts:
            if len(scrape_item.url.parts) == 4:
                return await self.video(scrape_item, video_id=scrape_item.url.parts[-1])

        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        player = soup.select_one(_SELECTORS.JS_PLAYER)
        if not player:
            raise ScrapeError(422)

        url: AbsoluteHttpURL = decode_video_url(player.text)
        m3u8_media = M3U8Media(await self._get_m3u8(url))
        model_name = soup.select_one(_SELECTORS.MODEL_NAME).get_text(strip=True)

        filename, ext = self.get_filename_and_ext(f"{model_name} [{video_id}].mp4")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8_media=m3u8_media)


def decode_video_url(script_text: str) -> AbsoluteHttpURL:
    url = get_text_between(script_text, 'file: f("', '"),')
    # cut first and last 16 characters, reverse, base64 decode
    return AbsoluteHttpURL(binascii.a2b_base64(url[-17:15:-1]).decode())
