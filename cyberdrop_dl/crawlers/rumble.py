from __future__ import annotations

import dataclasses
import json
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar, override

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import Resolution, Subtitle
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld, m3u8, parse_url, traversal
from cyberdrop_dl.utils._url import remove_query_params
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    import yarl
    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


class LiveStatus(IntEnum):
    NOT_LIVE = 0
    LIVE_ENDED = 1
    CURRENTLY_LIVE = 2


class FormatType(IntEnum):
    HLS = 1
    WEBM = 2
    MP4 = 3


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class Metadata:
    bitrate: int = 0
    size: int = 0
    w: int = 0
    h: int = 0


@dataclasses.dataclass(slots=True, frozen=True, order=True)
class Format:
    resolution: Resolution
    is_single_file: bool  # for formats with the same resolution, give priority to non hls
    bitrate: int
    size: int
    type: FormatType  #  On formats where everything else is the same, choose mp4 over webm
    url: AbsoluteHttpURL
    m3u8: m3u8.Rendition | None = None


@dataclasses.dataclass(slots=True, frozen=True)
class Video:
    id: str
    title: str
    upload_date: str
    url: AbsoluteHttpURL
    formats: tuple[Format, ...]
    subtitles: tuple[Subtitle, ...]
    thumb: str | None = None


@HTTPConfig(impersonate="firefox", rate_limit=(8, 1))
class RumbleCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Channel": "/c/<name>",
        "Channel videos": "/c/<name>/videos",
        "Channel shorts": "/c/<name>/shorts",
        "User": "/user/<name>",
        "Video": "<video_id>-<video-title>.html",
        "Short": "/shorts/<short_id>",
        "Embed": "/embed/<video_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://rumble.com")
    DOMAIN: ClassVar[str] = "rumble"
    NEXT_PAGE_SELECTOR: ClassVar[str] = "nav a[href*=page]:has(svg[stroke-linecap=round])"

    def __post_init__(self) -> None:
        self.api: RumbleAPI = RumbleAPI.from_crawler(self)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["embed", video_id] if video_id.startswith("v"):
                await self.embed(scrape_item, video_id)
            case ["shorts", video_id]:
                await self.short(scrape_item, video_id)
            case [slug] if slug.startswith("v") and slug.endswith(".html"):
                await self.video(scrape_item)
            case ["c" | "user", user_name, "shorts"]:
                await self.channel_shorts(scrape_item, user_name)
            case ["c" | "user", user_name, "videos"]:
                await self.channel_videos(scrape_item, user_name)
            case ["c" | "user", _user_name]:
                await self.channel(scrape_item)
            case _:
                raise ValueError

    @override
    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return remove_query_params(super().transform_url(url), keep=("page",))

    @error_handling_wrapper
    async def channel_shorts(self, scrape_item: ScrapeItem, name: str) -> None:
        scrape_item.setup_as_album(self.create_title(name))
        scrape_item.append_folders("shorts")
        async for soup in self.web_pager(scrape_item.url):
            for short in map(_parse_short, _find_video_objs(soup)):
                new_item = scrape_item.create_child(short.url)
                self.create_eager_task(self._video(new_item, short))
                scrape_item.add_children()

    @override
    @classmethod
    def parse_url(
        cls, url: yarl.URL | str, /, relative_to: AbsoluteHttpURL | None = None, *, trim: bool | None = None
    ) -> AbsoluteHttpURL:
        return remove_query_params(super().parse_url(url, relative_to, trim=trim), keep=("page",))

    @error_handling_wrapper
    async def channel(self, scrape_item: ScrapeItem) -> None:
        for part in ("shorts", "videos"):
            self.create_task(self.run(scrape_item.create_child(scrape_item.url / part)))

    @error_handling_wrapper
    async def channel_videos(self, scrape_item: ScrapeItem, name: str) -> None:
        scrape_item.setup_as_album(self.create_title(name))
        async for soup in self.web_pager(scrape_item.url):
            for item in _find_video_objs(soup):
                new_item = scrape_item.create_child(self.parse_url(item["url"]))
                self.create_task(self.video(new_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def short(self, scrape_item: ScrapeItem, short_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        video = await self.api.short(short_id)
        await self._video(scrape_item, video)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        embed_id = self.parse_url(json_ld.find_attr(soup, "embedUrl")).name
        await self.embed(scrape_item, embed_id)

    @error_handling_wrapper
    async def embed(self, scrape_item: ScrapeItem, embed_id: str) -> None:
        video = await self.api.embed(embed_id)
        await self._video(scrape_item, video)

    @error_handling_wrapper
    async def _video(self, scrape_item: ScrapeItem, video: Video) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        best_format = max(await self._resolve_formats(video.formats))
        if best_format.m3u8:
            ext = ".mp4"
        else:
            _, ext = self.get_filename_and_ext(best_format.url.name)

        video_name = self.create_custom_filename(video.title, ext, file_id=video.id, resolution=best_format.resolution)
        scrape_item.uploaded_at = self.parse_iso_date(video.upload_date)
        scrape_item.url = video.url
        self.create_eager_task(
            self.handle_file(
                best_format.url,
                scrape_item,
                f"{video.title}{ext}",
                ext,
                custom_filename=video_name,
                m3u8=best_format.m3u8,
                thumbnail=video.thumb,
            )
        )
        self.handle_subs(scrape_item, video_name, video.subtitles)

    async def _resolve_formats(self, formats: Iterable[Format]) -> list[Format]:
        async def resolve_m3u8(fmt: Format) -> Format:
            if fmt.is_single_file:
                return fmt

            m3u8, info = await self.request_m3u8_playlist(fmt.url)
            return dataclasses.replace(
                fmt,
                resolution=info.resolution,
                m3u8=m3u8,
                bitrate=info.stream_info.bandwidth or 0,
            )

        return await aio.map(resolve_m3u8, formats, task_limit=10)


class RumbleAPI(API):
    async def embed(self, embed_id: str) -> Video:
        api_url = (self.PRIMARY_URL / "embedJS/u3").with_query(request="video", ver=2, v=embed_id)
        data: dict[str, Any] = await self.request_json(api_url)

        if data.get("live") == LiveStatus.CURRENTLY_LIVE:
            raise ScrapeError(422, "livestreams are not supported")

        return Video(
            id=embed_id,
            upload_date=data["pubDate"],
            title=css.unescape(data["title"]),
            url=self.parse_url(data["l"]),
            formats=tuple(_parse_formats(data.get("ua") or {})),
            subtitles=tuple(_parse_subs(data.get("cc") or {})),
        )

    async def short(self, short_id: str) -> Video:
        soup = await self.request_soup(self.PRIMARY_URL / "shorts" / short_id)
        for obj in _find_video_objs(soup):
            if obj.get("permalink_id") == short_id:
                short = obj
                break
        else:
            raise ScrapeError(422, "Unable to find short data")
        return _parse_short(short)


def _parse_short(short: dict[str, Any]) -> Video:
    return Video(
        id=short["permalink_id"],
        upload_date=short["upload_date"],
        title=css.unescape(short["title"]),
        url=RumbleCrawler.parse_url(short["url"]),
        formats=tuple(_parse_short_formats(short["videos"])),
        subtitles=(),
        thumb=short.get("thumb"),
    )


def _find_video_objs(soup: BeautifulSoup) -> Generator[dict[str, Any]]:
    for script in css.iselect_text(
        soup,
        selector="script[type='application/json'], script[type='application/ld+json']",
        contains="object_type",
    ):
        for _, obj in traversal.find_objs(
            json.loads(script),
            validate={
                "object_type": "video",
            },
        ):
            yield obj


def _filter_formats[T](fmts: Iterable[tuple[str, T]]) -> Generator[tuple[FormatType, T]]:
    for type_, fmt in fmts:
        if type_ in {"audio", "tar", "timeline"}:
            continue

        try:
            f_type = FormatType[type_.upper()]
        except KeyError:
            raise ScrapeError(422, f"Video has an unknown format type: {type_}") from None

        yield f_type, fmt


def _parse_short_formats(formats: Iterable[dict[str, Any]]) -> Generator[Format]:
    for type_, fmt in _filter_formats((fmt["type"], fmt) for fmt in formats):
        is_single_file = type_ is not FormatType.HLS
        yield Format(
            resolution=Resolution.parse(fmt["resolution"]) if is_single_file else Resolution.unknown(),
            is_single_file=is_single_file,
            bitrate=fmt.get("bitrate_kbps", 0),
            size=0,
            type=type_,
            url=parse_url(fmt["url"]),
        )


def _parse_formats(formats: dict[str, list[dict[str, Any]] | dict[str, dict[str, Any]]]) -> Generator[Format]:
    for type_, format_options in _filter_formats(formats.items()):
        pairs = ((None, f) for f in format_options) if isinstance(format_options, list) else format_options.items()
        is_single_file = type_ is not FormatType.HLS

        for height, fmt in pairs:
            url = parse_url(fmt["url"])
            meta = Metadata(**(fmt.get("meta") or {}))

            if meta.w and meta.h:
                resolution = Resolution(meta.w, meta.h)

            elif height and height != "auto":
                resolution = Resolution.parse(height)

            else:
                resolution = Resolution.unknown()

            yield Format(resolution, is_single_file, meta.bitrate, meta.size, type_, url)


def _parse_subs(subs: dict[str, dict[str, str]]) -> Generator[Subtitle]:
    for code, sub in subs.items():
        yield Subtitle(
            url=sub["path"],
            lang_code=code.replace("-auto", ".auto"),
            name=sub.get("language"),
        )
