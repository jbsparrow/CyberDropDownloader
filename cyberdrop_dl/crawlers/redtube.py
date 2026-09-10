from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar, override

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import extr_text, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.url_objects import ScrapeItem


class RedtubeCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        " Video": (
            "/<video_id>",
            "?id=<video_id>",
        ),
    }

    DOMAIN: ClassVar[str] = "redtube"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.redtube.com")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case [video_id] if video_id.isdecimal():
                await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        if "embed." in url.host and (video_id := url.query.get("id")):
            return cls.PRIMARY_URL / video_id
        return url

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request(scrape_item.url) as resp:
            hls_src = _extract_hls_source(await resp.text())
            _, props = json_ld.find(await resp.soup())

        scrape_item.uploaded_at = self.parse_iso_date(props["uploadDate"])
        name: str = props["name"]

        sources = await self.request_json(hls_src)
        _, m3u8_url = max(_parse_sources(sources))

        m3u8, info = await self.request_m3u8_playlist(m3u8_url)
        filename = self.create_custom_filename(
            name,
            ext := ".mp4",
            file_id=video_id,
            resolution=info.resolution,
            video_codec=info.codecs.video,
            audio_codec=info.codecs.audio,
        )
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            name,
            ext,
            m3u8=m3u8,
            custom_filename=filename,
            thumbnail=self.parse_url(props["thumbnailUrl"]),
        )


def _extract_hls_source(html: str) -> AbsoluteHttpURL:
    player = extr_text(html, "playervars:", "viewUrl").strip(",").strip()
    player_vars = json.loads(player)
    for media in player_vars.get("mediaDefinitions", ()):
        if media.get("format") == "hls":
            return RedtubeCrawler.parse_url(media["videoUrl"])

    raise ScrapeError(422, "Unable to extract HLS source")


def _parse_sources(sources: list[dict[str, Any]]) -> Generator[tuple[Resolution, AbsoluteHttpURL]]:
    for source in sources:
        res = Resolution.parse(source["quality"])
        url = RedtubeCrawler.parse_url(source["videoUrl"])
        yield res, url
