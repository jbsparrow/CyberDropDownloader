from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar, Literal

from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.dataclass import deserialize
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@Crawler.db_path_builder("name")
class LividCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/embed/<video_id>",
            "/watch/<video_id>",
        )
    }
    DOMAIN: ClassVar[str] = "livid.com"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://livid.com")

    def __post_init__(self) -> None:
        self.api: LividAPI = LividAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["embed" | "watch", video_id]:
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete(scrape_item.url):
            return

        video = await self.api.video(video_id, scrape_item.get_referer())
        scrape_item.uploaded_at = self.parse_iso_date(video.createdAt)
        await self._video(scrape_item, video)

    async def _video(self, scrape_item: ScrapeItem, video: Video) -> None:
        m3u8 = info = debrid_link = None
        referer = scrape_item.get_referer() or self.PRIMARY_URL
        if video.allowDownloads and (renditions := await self.api.renditions(video.id, referer)):
            res, rendition_id = max(renditions)
            debrid_link, ext = await self.api.link(video.id, rendition_id, referer)
            _, ext = self.get_filename_and_ext(video.id + ext)  # Check ext is valid
        else:
            m3u8, info = await self.request_m3u8_playlist(video.m3u8)
            res, ext = info.resolution, ".mp4"

        await self.handle_file(
            scrape_item.url,
            scrape_item,
            video.title,
            ext,
            m3u8=m3u8,
            custom_filename=self.create_custom_filename(video.title, ext, file_id=video.slug, resolution=res),
            thumbnail=video.thumb,
            debrid_link=debrid_link,
            headers={"Referer": str(referer)},
        )


type Rendition = tuple[Resolution, str]


# ruff: noqa: N815
@dataclasses.dataclass(frozen=True, slots=True)
class Video:
    id: str
    slug: str
    title: str
    m3u8: AbsoluteHttpURL
    thumb: AbsoluteHttpURL
    createdAt: str
    allowDownloads: bool = False


class LividAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.livid.com/v1")

    async def video(self, slug: str, referer: AbsoluteHttpURL | None) -> Video:
        url = self.ENTRYPOINT / "videos/slug" / slug
        resp = await self.request_json(url, headers={"Referer": str(referer or self.PRIMARY_URL)})
        return deserialize(
            Video,
            resp,
            thumb=self.parse_url(resp["currentVideoThumbnail"]["src"]),
            m3u8=self.parse_url(resp["currentVideoAsset"]["src"]),
        )

    async def renditions(self, video_id: str, referer: AbsoluteHttpURL | None) -> list[Rendition]:
        url = self.ENTRYPOINT / "videos/id" / video_id / "renditions"
        resp = await self.request_json(url, headers={"Referer": str(referer or self.PRIMARY_URL)})
        if resp.get("encodeStatus") != "COMPLETED":
            return []

        return [(Resolution.parse(r["resolution"]), r["id"]) for r in resp["renditions"]]

    async def link(
        self,
        video_id: str,
        rendition_id: str,
        referer: AbsoluteHttpURL | None,
        *,
        format: Literal["mkv", "original"] = "original",  # noqa: A002
    ) -> tuple[AbsoluteHttpURL, str]:
        url = self.ENTRYPOINT / "videos/id" / video_id / "renditions" / rendition_id / "link"
        resp = await self.request_json(
            url,
            method="POST",
            json={"format": format},
            headers={
                "Referer": str(referer or self.PRIMARY_URL),
            },
        )
        return self.parse_url(resp["url"]), f".{resp['fileExtension']}"
