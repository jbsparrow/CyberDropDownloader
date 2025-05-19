from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from fractions import Fraction
from functools import cached_property
from typing import TYPE_CHECKING, NamedTuple

from m3u8 import M3U8 as _M3U8
from m3u8 import Media, Playlist

from cyberdrop_dl.utils.utilities import parse_url

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from m3u8.model import StreamInfo
    from yarl import URL

RESOLUTION_REGEX = [
    re.compile(regex)
    for regex in [
        r"(?P<width>\d+)x(?P<height>\d+)",  # ex: 1920x1080
        r"(?P<height_p>\d+)p",  # ex: 1080p, 720p
    ]
]


VIDEO_CODECS = "avc1", "avc2", "avc3", "avc4", "av1", "hevc", "hev1", "hev2", "hvc1", "hvc2", "vp8", "vp9", "vp10"
AUDIO_CODECS = "ac-3", "ec-3", "mp3", "mp4a", "opus", "vorbis"


class Codecs(NamedTuple):
    video: str
    audio: str | None

    @staticmethod
    def parse(codecs: str) -> Codecs:
        video_codec = audio_codec = None

        def codec_or_none(codec: str, lookup_array: Iterable[str]) -> str | None:
            codec, *_ = codec.split(".")
            clean_codec = codec[:-1].replace("0", "") + codec[-1]
            return next((key for key in lookup_array if clean_codec.startswith(key)), None)

        for codec in codecs.split(","):
            if not video_codec and (found := codec_or_none(codec, VIDEO_CODECS)):
                video_codec = found
            elif not audio_codec and (found := codec_or_none(codec, AUDIO_CODECS)):
                audio_codec = found
            if video_codec and audio_codec:
                break

        assert video_codec
        if "avc" in video_codec:
            video_codec = "avc1"
        elif "hev" in video_codec or "hvc" in video_codec:
            video_codec = "hevc"
        return Codecs(video_codec, audio_codec)


class Resolution(NamedTuple):
    width: int
    height: int

    def name(self) -> str:
        if 7600 < self.width < 8200:
            return "8K"
        if 3800 < self.width < 4100:
            return "4K"
        return f"{self.height}p"

    def aspect_ratio(self) -> Fraction:
        return Fraction(self.width, self.height)


RESOLUTIONS = [
    Resolution(*resolution)  # Best to worst
    for resolution in [
        (7680, 4320),
        (3840, 2160),
        (2560, 1440),
        (1920, 1080),
        (1280, 720),
        (640, 480),
        (640, 360),
        (480, 320),
        (426, 240),
        (320, 240),
        (256, 144),
    ]
]


class MediaType(StrEnum):
    audio = "AUDIO"
    video = "VIDEO"
    subtitles = "SUBTITLES"
    closed_captions = "CLOSED-CAPTIONS"


class MediaList(list[Media]):
    def filter_by(
        self,
        type: MediaType | str | None = None,
        group_id: str | None = None,
        language: str | None = None,
        name: str | None = None,
    ) -> Generator[Media]:
        assert any(value is not None for value in (type, group_id, language, name))
        attrs = {name: value for name, value in locals().items() if value is not None and name != "self"}
        for media in self:
            if all(getattr(media, name) == value for name, value in attrs.items()):
                yield media

    def filter(
        self,
        type: MediaType | str | None = None,
        group_id: str | None = None,
        language: str | None = None,
        name: str | None = None,
    ) -> MediaList:
        return MediaList(self.filter_by(type, group_id, language, name))

    def get_default(self) -> Media | None:
        if self:
            for media in self:
                if media.default == "YES":
                    return media

            for media in self:
                if media.autoselect == "YES":
                    return media


class MediaURLs(NamedTuple):
    video: URL
    audio: URL | None
    subtitle: URL | None


@dataclass(frozen=True, slots=True, order=True)
class RenditionGroup:
    resolution: Resolution
    codecs: Codecs
    stream_info: StreamInfo
    media: MediaList
    urls: MediaURLs

    @staticmethod
    def new(playlist: Playlist) -> RenditionGroup:
        assert playlist.uri
        assert playlist.stream_info.codecs

        def get_url(m3u8_obj: Playlist | Media) -> URL:
            return parse_url(m3u8_obj.absolute_uri, trim=False)

        video_url = get_url(playlist)
        subtitle_url = audio_url = None

        if playlist.stream_info.resolution is not None:
            resolution: Resolution = Resolution(*playlist.stream_info.resolution)
        else:
            resolution = get_resolution_from_url(video_url)

        codecs = Codecs.parse(playlist.stream_info.codecs)
        media = MediaList(playlist.media)

        if audio_group_id := playlist.stream_info.audio:
            audio = next(media.filter_by(type=MediaType.audio, group_id=audio_group_id))
            audio_url: URL | None = get_url(audio)

        if subtitle_group_id := playlist.stream_info.subtitles:
            subtitle = next(media.filter_by(type=MediaType.subtitles, group_id=subtitle_group_id))
            subtitle_url: URL | None = get_url(subtitle)

        media_urls = MediaURLs(video_url, audio_url, subtitle_url)
        return RenditionGroup(resolution, codecs, playlist.stream_info, media, media_urls)


class M3U8(_M3U8):
    @cached_property
    def total_duration(self) -> timedelta:
        total_duration: float = sum(duration for segment in self.segments if (duration := segment.duration))
        return timedelta(seconds=total_duration)

    @staticmethod
    def new(m3u8_content: str, url: URL) -> M3U8:
        return M3U8(m3u8_content, base_uri=str(url.parent))

    @property
    def is_master_playlist(self):
        return self.is_variant or not self.segments

    def as_variant(self) -> VariantM3U8:
        return VariantM3U8(self)


class VariantM3U8:
    """M3U8 that has links to other M3U8s inside"""

    def __init__(self, m3u8: M3U8):
        assert m3u8.is_master_playlist
        self._m3u8 = m3u8
        self.groups = sorted((RenditionGroup.new(playlist) for playlist in m3u8.playlists), reverse=True)

    def get_rendition_groups(
        self, only: Iterable[str] = (), *, exclude: Iterable[str] = ()
    ) -> Generator[RenditionGroup]:
        """Yields M3U8 options, best to worst"""
        assert not (only and exclude)
        if isinstance(exclude, str):
            exclude = (exclude,)
        if isinstance(only, str):
            only = (only,)
        for group in self.groups:
            if only and group.codecs.video not in only:
                continue
            if group.codecs.video not in exclude:
                yield group

    def get_best_group(self, only: Iterable[str] = (), *, exclude: Iterable[str] = ()) -> RenditionGroup:
        return next(self.get_rendition_groups(only=only, exclude=exclude))


def get_resolution_from_url(url: URL | str) -> Resolution:
    if isinstance(url, str):
        url = parse_url(url, trim=False)  # Raises Invalid URL error for relative URLs

    for resolution in RESOLUTIONS:
        if str(resolution.height) in url.parts:
            return resolution

    for pattern in RESOLUTION_REGEX:
        if match := re.search(pattern, url.path):
            try:
                width = int(match.group("width"))
                height = int(match.group("height"))
                return Resolution(width, height)
            except (IndexError, KeyError):
                height_ = match.groupdict().get("height_p")
                if not height_:
                    continue

                height = int(height_)
                width = round(height * 16 / 9)  # Assume 16:9 aspect ratio
                return Resolution(width, height)

    raise RuntimeError("Unable to parse resolution")
