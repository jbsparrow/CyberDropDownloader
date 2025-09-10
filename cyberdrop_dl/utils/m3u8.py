from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from functools import cached_property
from typing import TYPE_CHECKING, Literal, NamedTuple

from m3u8 import M3U8 as _M3U8
from m3u8 import Media, Playlist

from cyberdrop_dl.data_structures.mediaprops import Codecs, Resolution
from cyberdrop_dl.utils.utilities import parse_url

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from m3u8.model import StreamInfo

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


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
            autoselect = None
            for media in self:
                if media.default == "YES":
                    return media
                if media.autoselect == "YES" and autoselect is None:
                    autoselect = media
            return autoselect


class MediaURLs(NamedTuple):
    video: AbsoluteHttpURL
    audio: AbsoluteHttpURL | None
    subtitle: AbsoluteHttpURL | None


class RenditionGroup(NamedTuple):
    video: M3U8
    audio: M3U8 | None = None
    subtitle: M3U8 | None = None


@dataclass(frozen=True, slots=True, order=True)
class RenditionGroupDetails:
    resolution: Resolution
    codecs: Codecs
    stream_info: StreamInfo
    media: MediaList
    urls: MediaURLs

    @staticmethod
    def new(playlist: Playlist) -> RenditionGroupDetails:
        assert playlist.uri

        def get_url(m3u8_obj: Playlist | Media) -> AbsoluteHttpURL:
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
            audio_url: AbsoluteHttpURL | None = get_url(audio)

        if subtitle_group_id := playlist.stream_info.subtitles:
            subtitle = next(media.filter_by(type=MediaType.subtitles, group_id=subtitle_group_id))
            subtitle_url: AbsoluteHttpURL | None = get_url(subtitle)

        media_urls = MediaURLs(video_url, audio_url, subtitle_url)
        return RenditionGroupDetails(resolution, codecs, playlist.stream_info, media, media_urls)


class M3U8(_M3U8):
    def __init__(
        self,
        content: str,
        base_uri: AbsoluteHttpURL | None = None,
        media_type: Literal["video", "audio", "subtitles"] | None = None,
    ) -> None:
        if base_uri and base_uri.suffix.casefold() == ".m3u8":
            base_uri = base_uri.parent
        self.media_type: Literal["video", "audio", "subtitles"] | None = media_type
        super().__init__(content, base_uri=str(base_uri) if base_uri else None)

    def __repr__(self) -> str:
        return (
            f"{type(self)}(media_type={self.media_type!r}, base_uri={self.base_uri!r}, is_variant={self.is_variant!r})"
        )

    @cached_property
    def total_duration(self) -> timedelta:
        total_duration: float = sum(duration for segment in self.segments if (duration := segment.duration))
        return timedelta(seconds=total_duration)


class VariantM3U8Parser:
    """Parses groups inside a variant M3U8"""

    def __init__(self, m3u8: M3U8) -> None:
        assert m3u8.is_variant
        self._m3u8 = m3u8
        self.groups = sorted((RenditionGroupDetails.new(playlist) for playlist in m3u8.playlists), reverse=True)

    def get_rendition_groups(
        self, only: Iterable[str] = (), *, exclude: Iterable[str] = ()
    ) -> Generator[RenditionGroupDetails]:
        """Yields M3U8 options, best to worst"""
        assert not (only and exclude), "only one of `only` or `exclude` can be supplied, not both"
        if isinstance(exclude, str):
            exclude = (exclude,)
        if isinstance(only, str):
            only = (only,)

        for group in self.groups:
            if codec := group.codecs.video:
                if only and codec not in only:
                    continue
                if codec in exclude:
                    continue
            yield group

    def get_best_group(self, only: Iterable[str] = (), *, exclude: Iterable[str] = ()) -> RenditionGroupDetails:
        return next(self.get_rendition_groups(only=only, exclude=exclude))


def get_best_group_from_playlist(
    m3u8_playlist: M3U8, only: Iterable[str] = (), *, exclude: Iterable[str] = ()
) -> RenditionGroupDetails:
    return VariantM3U8Parser(m3u8_playlist).get_best_group(only=only, exclude=exclude)


def get_resolution_from_url(url: AbsoluteHttpURL | str) -> Resolution:
    if isinstance(url, str):
        url = parse_url(url, trim=False)  # Raises Invalid URL error for relative URLs

    try:
        return Resolution.parse(url)
    except ValueError:
        raise RuntimeError(f"Unable to parse resolution from {url}") from None
