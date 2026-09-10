from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar, Self

from pydantic import dataclasses

from cyberdrop_dl import aio
from cyberdrop_dl.cache import disk_cached_method
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import ISO639Subtitle, Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL, MuxVideo, ScrapeItem
from cyberdrop_dl.utils import unique
from cyberdrop_dl.utils.dataclass import deserialize
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@HTTPConfig(rate_limit=(5, 1))
@Crawler.db_path_builder("url")
class PeerTubeGenericCrawler(Crawler, is_generic=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/w/<video_uuid>",
            "/w/<short_uuid>",
            "/videos/watch/<video_uuid>",
            "/videos/watch/<short_uuid>",
        ),
        "Playlist": "/w/p/<playlist_uuid>",
        "Account": "/a/<username>/videos",
        "Channel": "/c/<channel_uuid>",
    }
    DOMAIN: ClassVar[str] = "peertube"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://joinpeertube.org")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.DOMAIN = PeerTubeGenericCrawler.DOMAIN  # pyright: ignore[reportConstantRedefinition]

    def __post_init__(self) -> None:
        self.api: PeerTubeAPI = PeerTubeAPI.from_crawler(self)
        self.instance_locks: aio.WeakAsyncLocks[AbsoluteHttpURL] = aio.WeakAsyncLocks()
        self.good_hosts: set[AbsoluteHttpURL] = set()
        self.bad_hosts: set[AbsoluteHttpURL] = set()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["w", video_id] | ["videos", "watch", video_id]:
                await self.video(scrape_item, video_id)
            case ["a", playlist_id, "videos"]:
                await self.playlist(scrape_item, playlist_id, "accounts")
            case ["c", playlist_id]:
                await self.playlist(scrape_item, playlist_id, "video-channels")
            case ["w", "p", playlist_id]:
                await self.playlist(scrape_item, playlist_id, "video-playlists")
            case _:
                raise ValueError

    async def _check_node_info(self) -> None:
        if self.origin in self.good_hosts:
            return
        if self.origin in self.bad_hosts:
            raise NodeInfoError

        async with self.instance_locks[self.origin]:
            if self.origin in self.good_hosts:
                return
            if self.origin in self.bad_hosts:
                raise NodeInfoError

            node_info = await self.api.node_info()
            self.log.info("Server software running on %s:\n %s", self.origin, node_info["software"])
            self.good_hosts.add(self.origin)

    async def get_instances(self) -> tuple[str, ...]:
        try:
            return await self.api.instances()
        except Exception:
            self.log.exception("Unable to fetch additional PeerTube instances")
            return ()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        await self._check_node_info()
        video = await self.api.video(video_id, scrape_item.password)
        await self._video(scrape_item, video)

    async def _video(self, scrape_item: ScrapeItem, video: Video) -> None:
        scrape_item.uploaded_at = self.parse_iso_date(video.publishedAt)
        mux_streams = None
        best_video = max(f for f in video.files if f.hasVideo)
        if not best_video.hasAudio:
            best_audio = max((f for f in video.files if f.hasAudio and not f.hasVideo), key=lambda x: x.size)
            mux_streams = MuxVideo(best_video.fileUrl, best_audio.fileUrl)

        _, ext = self.get_filename_and_ext(best_video.fileUrl.name)
        filename = self.create_custom_filename(
            video.name, ext, file_id=video.uuid, resolution=best_video.resolution, fps=best_video.fps
        )
        subs = await self.api.captions(video.uuid, scrape_item.password)
        self.handle_subs(scrape_item, filename, subs)
        await self.handle_file(
            best_video.fileUrl,
            scrape_item,
            video.name,
            ext,
            custom_filename=filename,
            thumbnail=video.thumb,
            headers=self.api.headers(scrape_item.password),
            m3u8=mux_streams,
        )

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, playlist_id: str, kind: str) -> None:
        info = await self.api.playlist(playlist_id, kind)
        self.create_eager_task(self.write_metadata(scrape_item, playlist_id, info))
        scrape_item.setup_as_album(self.create_title(info["displayName"], playlist_id), album_id=playlist_id)

        async for video in self.api.playlist_videos(playlist_id, kind):
            self.create_task(self.run(scrape_item.create_child(video)))
            scrape_item.add_children()


class NodeInfoError(ScrapeError):
    def __init__(self, msg: str = "Unable to get nodeinfo from PeerTube instance") -> None:
        super().__init__("PeerTube Nodeinfo Error", msg)


@HTTPConfig(headers={"Accept": "application/json"})
class PeerTubeAPI(API):
    @classmethod
    def headers(cls, password: str | None) -> dict[str, Any]:
        return {"x-peertube-video-password": password} if password else {}

    async def pager(self, url: AbsoluteHttpURL, count: int = 30) -> AsyncGenerator[list[dict[str, Any]]]:
        for start in itertools.count(0, count):
            resp = await self.request_json(url.update_query(start=start, count=count))
            yield resp["data"]
            if len(resp["data"]) < count:
                break

    @disk_cached_method(ttl=30 * 86400)
    async def instances(self) -> tuple[str, ...]:
        self.log.info("Fetching list of PeerTube instances")
        url = AbsoluteHttpURL("https://instances.joinpeertube.org/api/v1/instances?healthy=true")
        hosts: set[str] = set()
        async for data in self.pager(url, count=1_000):
            hosts.update(inst["host"] for inst in data)

        return tuple(sorted(hosts))

    async def video(self, video_id: str, password: str | None) -> Video:
        url = self.origin / "api/v1/videos" / video_id
        resp = await self.request_json(url, headers=self.headers(password))
        return Video.parse(resp)

    async def captions(self, video_id: str, password: str | None) -> list[ISO639Subtitle]:
        url = self.origin / "api/v1/videos" / video_id / "captions"
        resp = await self.request_json(url, headers=self.headers(password))
        return [ISO639Subtitle(sub["fileUrl"], sub["language"]["id"], sub["language"]["label"]) for sub in resp["data"]]

    async def playlist(self, playlist_id: str, kind: str) -> dict[str, Any]:
        url = self.origin / "api/v1" / kind / playlist_id
        return await self.request_json(url)

    async def playlist_videos(self, playlist_id: str, kind: str) -> AsyncGenerator[AbsoluteHttpURL]:
        url = self.origin / "api/v1" / kind / playlist_id / "videos"
        async for data in self.pager(url.with_query(sort="-publishedAt", nsfw="both", isLive="false")):
            for video in data:
                uuid: str = video.get("shortUUID") or video["video"]["shortUUID"]
                yield self.origin / "w" / uuid

    async def node_info(self) -> dict[str, Any]:
        # https://nodeinfo.diaspora.software/protocol.html
        url = self.origin / ".well-known/nodeinfo"

        try:
            resp = await self.request_json(url)
        except Exception as e:
            raise NodeInfoError from e

        try:
            for link in resp["links"]:
                rel: str = link["rel"]
                if rel.startswith("http://nodeinfo.diaspora.software/ns/schema"):
                    return await self.request_json(self.parse_url(link["href"]))

        except Exception as e:
            raise NodeInfoError("PeerTube instance does not support the nodeinfo protocol") from e

        raise NodeInfoError("PeerTube instance does not support the nodeinfo protocol")


@dataclasses.dataclass(slots=True, frozen=True)
class Video:
    uuid: str
    name: str
    url: AbsoluteHttpURL
    thumb: AbsoluteHttpURL
    publishedAt: str
    files: tuple[File, ...]

    @classmethod
    def parse(cls, video: dict[str, Any]) -> Self:
        if video.get("isLive"):
            raise ScrapeError(422, "Livestreams are not supported")

        *_, thumb = max((t["width"], t["height"], t["fileUrl"]) for t in video["thumbnails"])

        files = unique(
            itertools.chain(
                itertools.chain.from_iterable(p["files"] for p in video["streamingPlaylists"]),
                video["files"],
            ),
            key=lambda x: x["id"],
        )
        return deserialize(cls, video, thumb=thumb, files=map(File.parse, files))


# ruff: noqa: N815
@dataclasses.dataclass(slots=True, frozen=True, order=True)
class File:
    resolution: Resolution | None
    fps: int | None
    size: int
    id: int
    fileUrl: AbsoluteHttpURL
    hasAudio: bool
    hasVideo: bool

    @classmethod
    def parse(cls, file: dict[str, Any]) -> Self:
        return deserialize(
            cls,
            file,
            resolution=Resolution(file["width"], file["height"]) if file.get("hasVideo") else None,
        )


class PeerTubeCrawler(PeerTubeGenericCrawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = ("peertube",)
