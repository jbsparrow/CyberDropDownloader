from __future__ import annotations

from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple, Self

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

PRIMARY_BASE_DOMAIN = URL("https://dailymotion.com/")


class Format(NamedTuple):
    resolution: str  # '1080','720','480','380','240','144' or 'auto'
    url: URL


@dataclass(frozen=True)
class Video:
    access_id: str
    title: str = ""
    qualities: tuple[Format, ...] = ()
    playlist_id: str | None = None
    is_password_protected: bool = False
    created_time: int | None = None

    @property
    def url(self) -> URL:
        return PRIMARY_BASE_DOMAIN / "video" / self.access_id

    @property
    def best_quality(self) -> Format:
        # Try to get the best not hls quality
        matches = [q for q in self.qualities if q.url.suffix != ".m3u8"]
        matches = matches or self.qualities
        return sorted(matches)[-1]

    @property
    def metadata_url(self) -> URL:
        return PRIMARY_BASE_DOMAIN / "player/metadata/video" / self.access_id

    @classmethod
    def from_url(cls, url: URL) -> Self:
        video_id = get_video_id(url)
        return cls(video_id)


VIDEO_INFO_KEYS = [f.name for f in fields(Video)]


class DailymotionCrawler(Crawler):
    SUPPORTED_SITES = MappingProxyType({"dailymotion": ["dailymotion", "dai.ly"]})  # type: ignore
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager, _) -> None:
        super().__init__(manager, "dailymotion", "Dailymotion")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "video" in scrape_item.url.parts:
            return await self.video(scrape_item)
        if "playlist" in scrape_item.url.parts:
            return await self.playlist(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an video."""

        video = Video.from_url(scrape_item.url)
        if await self.check_complete_from_referer(video.url):
            return

        scrape_item.url = video.url
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.domain, video.metadata_url)

        video = self.get_full_video_info(json_resp)
        link = video.best_quality.url
        if link.suffix == ".m3u8":
            raise ScrapeError(422)
        if video.is_password_protected:
            raise ScrapeError(401)

        scrape_item.possible_datetime = video.created_time
        filename, ext = get_filename_and_ext(video.title + link.suffix)
        await self.handle_file(link, scrape_item, filename, ext)

    def get_full_video_info(self, json_resp: dict) -> Video:
        video_info = {k: v for k, v in json_resp.items() if k in VIDEO_INFO_KEYS}
        qualities: dict = video_info["qualities"]
        formats = []
        for resolution in qualities:
            link_str = qualities[resolution][0]["url"]
            link = self.parse_url(link_str)
            formats.append(Format(resolution, link))

        video_info["qualities"] = tuple(formats)
        return Video(**video_info)


def get_video_id(url: URL) -> str:
    if "dai.ly" in url.host:  # type: ignore
        return url.parts[1]
    video_id_index = url.parts.index("video") + 1
    video_id = url.parts[video_id_index]
    return video_id.rsplit("_", 1)[0]
