from __future__ import annotations

import dataclasses
import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal, Unpack

from cyberdrop_dl import aio, ffmpeg
from cyberdrop_dl.exceptions import DownloadError, ScrapeError
from cyberdrop_dl.utils import m3u8

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyberdrop_dl.clients import HttpMethod
    from cyberdrop_dl.clients.request import RequestParams
    from cyberdrop_dl.url_objects import AbsoluteHttpURL

logger = logging.getLogger(__name__)


def check_ffmpeg_is_installed() -> None:
    if ffmpeg.is_installed():
        return
    msg = "ffmpeg is not installed and it is required for HLS downloads"
    if os.name == "nt":
        msg += ". Get it from: https://www.gyan.dev/ffmpeg/builds/"

    raise DownloadError("FFmpeg Not Installed", msg)


class HLSMixin(ABC):
    """Class to fetch and parse HTTP live streams

    For multi variant m3u8, the best resolution will be automatically selected"""

    @abstractmethod
    async def request_text(
        self,
        url: AbsoluteHttpURL,
        /,
        method: HttpMethod = "GET",
        **kwargs: Unpack[RequestParams],
    ) -> str: ...

    async def request_m3u8(
        self,
        url: AbsoluteHttpURL,
        /,
        method: HttpMethod = "GET",
        only: Iterable[str] = (),
        exclude: Iterable[str] = ("vp09",),
        keep_query: bool = False,  # noqa: FBT001, FBT002
        **kwargs: Unpack[RequestParams],
    ) -> tuple[m3u8.Rendition, m3u8.RenditionDetails | None]:
        m3u8_obj = await self._request_m3u8(url, method, **kwargs)
        if m3u8_obj.is_variant:
            logger.info("Selecting best rendition from %s", url)
            rendition = m3u8.select_best_rendition(m3u8_obj, only=only, exclude=exclude)
            if keep_query:
                rendition = dataclasses.replace(rendition, urls=rendition.urls.with_query(url.query))

            logger.info("Selected best rendition for %s:\n%s", url, rendition)
            return await self._resolve_rendition(rendition, method, **kwargs)
        m3u8_obj.media_type = "video"
        return m3u8.Rendition(m3u8_obj, None, None), None

    async def _resolve_rendition(
        self,
        rendition: m3u8.RenditionDetails,
        /,
        method: HttpMethod = "GET",
        **kwargs: Unpack[RequestParams],
    ) -> tuple[m3u8.Rendition, m3u8.RenditionDetails]:

        async def resolve(media_type: Literal["video", "audio", "subtitle"]) -> m3u8.M3U8 | None:
            url: AbsoluteHttpURL | None = getattr(rendition.urls, media_type)
            if not url:
                return None
            return await self._request_m3u8(url, method, media_type, **kwargs)

        video, audio, subs = await aio.gather(resolve("video"), resolve("audio"), resolve("subtitle"))
        assert video
        return m3u8.Rendition(video, audio, subs), rendition

    async def _request_m3u8(
        self,
        url: AbsoluteHttpURL,
        /,
        method: HttpMethod = "GET",
        media_type: Literal["video", "audio", "subtitle"] | None = None,
        **kwargs: Unpack[RequestParams],
    ) -> m3u8.M3U8:
        check_ffmpeg_is_installed()
        content = await self.request_text(url, method, **kwargs)
        return m3u8.M3U8(content, url.parent, media_type, source=url)

    async def request_m3u8_playlist(
        self,
        url: AbsoluteHttpURL,
        /,
        method: HttpMethod = "GET",
        only: Iterable[str] = (),
        exclude: Iterable[str] = ("vp09",),
        keep_query: bool = False,  # noqa: FBT001, FBT002
        **kwargs: Unpack[RequestParams],
    ) -> tuple[m3u8.Rendition, m3u8.RenditionDetails]:
        """Get m3u8 rendition group from a playlist m3u8 (variant m3u8), selecting the best format"""
        playlist, info = await self.request_m3u8(
            url, method, only=only, exclude=exclude, keep_query=keep_query, **kwargs
        )
        if info is None:
            raise ScrapeError(422, "Not a variant m3u8", origin=url)
        return playlist, info
