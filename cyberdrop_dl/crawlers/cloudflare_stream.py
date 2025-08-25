"""
https://www.cloudflare.com/developer-platform/products/cloudflare-stream/
https://developers.cloudflare.com/stream/
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.json import is_jwt, jwt_decode
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_DEFAULT_VIDEO_CDN = AbsoluteHttpURL("https://watch.cloudflarestream.com")


class CloudflareStreamCrawler(Crawler):
    SUPPORTED_DOMAINS = "videodelivery.net", "cloudflarestream.com"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Public Video": (
            "/embed/___.js?video=<video_uid>",
            "/<video_uid>/watch",
            "/<video_uid>/iframe",
            "/<video_uid>",
        ),
        "Restricted Access Video": (
            "/embed/___.js?video=<jwt_access_token>",
            "/<jwt_access_token>/watch",
            "/<jwt_access_token>/iframe",
            "/<jwt_access_token>",
        ),
    }

    DOMAIN = "cloudflarestream"
    FOLDER_DOMAIN = "CloudflareStream"
    PRIMARY_URL = AbsoluteHttpURL("https://cloudflarestream.com")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["embed", _] if video_id := scrape_item.url.query.get("video"):
                return await self.video(scrape_item, video_id)
            case [video_id, *_]:
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        is_expired: bool = False
        token = None
        if is_jwt(video_id):
            # https://developers.cloudflare.com/stream/viewing-videos/securing-your-stream/
            token = video_id
            payload = jwt_decode(token)
            video_id = payload["sub"]
            if expires := payload.get("exp"):
                is_expired = time.time() > expires

        _ = uuid.UUID(hex=video_id)  # raise ValueError if video_id is not a valid uuid
        scrape_item.url = _DEFAULT_VIDEO_CDN / video_id
        return await self._video(scrape_item, video_id, token, is_expired)

    @error_handling_wrapper
    async def _video(self, scrape_item: ScrapeItem, video_id: str, token: str | None, is_expired: bool) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        if is_expired:
            raise ScrapeError(401, "Access token to the video has expired")

        m3u8_url = self.PRIMARY_URL / (token or video_id) / "manifest/video.m3u8"
        m3u8, info = await self.get_m3u8_from_playlist_url(m3u8_url)
        filename, ext = self.get_filename_and_ext(video_id + ".mp4")
        custom_filename = self.create_custom_filename(
            video_id,
            ext,
            file_id=video_id,
            resolution=info.resolution,
            video_codec=info.codecs.video,
            audio_codec=info.codecs.audio,
        )
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, m3u8=m3u8, custom_filename=custom_filename)
