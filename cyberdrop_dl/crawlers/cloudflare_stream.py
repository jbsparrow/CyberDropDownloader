"""
https://www.cloudflare.com/developer-platform/products/cloudflare-stream/
https://developers.cloudflare.com/stream/
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.json import JSONWebToken, is_jwt
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_DEFAULT_VIDEO_CDN = AbsoluteHttpURL("https://watch.cloudflarestream.com")


class CloudflareStreamCrawler(Crawler):
    SUPPORTED_DOMAINS: SupportedDomains = "videodelivery.net", "cloudflarestream.com"
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

    DOMAIN: ClassVar[str] = "cloudflarestream"
    FOLDER_DOMAIN: ClassVar[str] = "CloudflareStream"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://cloudflarestream.com")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["embed", _] if video_id := scrape_item.url.query.get("video"):
                return await self.video(scrape_item, video_id)
            case [video_id, *_]:
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if is_jwt(video_id):
            # https://developers.cloudflare.com/stream/viewing-videos/securing-your-stream/
            token = video_id
            jwt = JSONWebToken.decode(token)
            video_id = jwt.payload["sub"]
            if jwt.is_expired():
                self.raise_exc(scrape_item, ScrapeError(401, "Access token to the video has expired"))
                return
        else:
            token = None

        _ = uuid.UUID(hex=video_id)  # raise ValueError if video_id is not a valid uuid
        scrape_item.url = _DEFAULT_VIDEO_CDN / video_id
        return await self._video(scrape_item, video_id, token)

    @error_handling_wrapper
    async def _video(self, scrape_item: ScrapeItem, video_id: str, token: str | None) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

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
