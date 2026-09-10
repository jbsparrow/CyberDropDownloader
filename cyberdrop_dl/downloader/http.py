from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, final

from aiohttp import ClientConnectorError, ClientError, ClientResponseError

from cyberdrop_dl import aio, constants, env, ffmpeg, storage
from cyberdrop_dl.clients.downloads import filter_by_duration, resolve_download_dir
from cyberdrop_dl.downloader import hls
from cyberdrop_dl.exceptions import (
    DownloadError,
    DurationError,
    InsufficientFreeSpaceError,
    InvalidContentTypeError,
    RestrictedDateRangeError,
    RestrictedFiletypeError,
    SkipDownloadError,
)
from cyberdrop_dl.hasher import compute_in_place_hash
from cyberdrop_dl.progress.scraping import show_msg
from cyberdrop_dl.signature import simple_repr
from cyberdrop_dl.url_objects import MuxVideo
from cyberdrop_dl.utils import dates
from cyberdrop_dl.utils.errors import error_handling_wrapper
from cyberdrop_dl.utils.m3u8 import Rendition

if TYPE_CHECKING:
    import datetime
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.clients.downloads import DownloadClient
    from cyberdrop_dl.config import Config
    from cyberdrop_dl.manager import Manager
    from cyberdrop_dl.progress.scraping import ScrapingUI
    from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem

logger = logging.getLogger(__name__)


_KNOWN_BAD_URLS = {
    "https://i.imgur.com/removed.png": 404,
    "https://saint2.su/assets/notfound.gif": 404,
    "https://bnkr.b-cdn.net/maintenance-vid.mp4": 503,
    "https://bnkr.b-cdn.net/maintenance.mp4": 503,
    "https://c.bunkr-cache.se/maintenance-vid.mp4": 503,
    "https://c.bunkr-cache.se/maintenance.jpg": 503,
}


_GENERIC_CRAWLERS = ".", "no_crawler"
_FILE_LOCKS: aio.WeakAsyncLocks[str] = aio.WeakAsyncLocks()
_NULL_CONTEXT: contextlib.nullcontext[None] = contextlib.nullcontext()


@contextlib.asynccontextmanager
async def _exclusive_lock(media_item: MediaItem) -> AsyncGenerator[None]:
    async with _FILE_LOCKS[media_item.filename]:
        logger.debug(f"Lock for '{media_item.filename}' acquired")
        try:
            yield
        finally:
            logger.debug(f"Lock for '{media_item.filename}' released")


@dataclasses.dataclass(slots=True)
class Capacity:
    limit: int | None = None
    waiting: int = 0
    condition: asyncio.Condition = dataclasses.field(default_factory=asyncio.Condition)
    _should_warn: bool = True

    @property
    def overloaded(self) -> bool:
        if self.limit is None:
            return False
        return self.waiting > max((self.limit * 1.2), self.limit + 10)

    async def _wait(self) -> None:
        if self.limit is None or self.waiting <= self.limit:
            return

        async with self.condition:
            await self.condition.wait()

    async def wait(self, domain: str) -> None:
        overloaded = self.overloaded
        if overloaded and self._should_warn:
            logger.warning(
                "[%s] Too many downloads queued (%s+). All scraping has been temporarily paused",
                domain,
                self.limit,
            )
            self._should_warn = False

        await self._wait()
        if overloaded and not self.overloaded:
            logger.debug("[%s] Resuming scraping", domain)
            self._should_warn = True


class Downloader:
    """High level class that handles limiters, database checks, skip by config checks and retries"""

    SUPPORTS_RETRIES: ClassVar[bool] = True
    log_prefix: str = "Download"

    @final
    def __init__(self, manager: Manager, slots: int | None = None, *, use_server_lock: bool = False) -> None:
        self.manager: Manager = manager
        self.use_server_lock: bool = use_server_lock
        self.capacity: Capacity = Capacity()
        self.config: Config = self.manager.config
        self._processed_items: set[str] = set()
        self._current_attempt_filesize: dict[str, int] = {}
        self._server_locks: aio.WeakAsyncLocks[str] = aio.WeakAsyncLocks()
        self._slots: int | None = slots
        self._semaphore: asyncio.Semaphore
        self._set_capacity_limit(slots)
        self.__post_init__()

    def __post_init__(self) -> None: ...

    __repr__ = simple_repr("slots", "use_server_lock", "log_prefix", "capacity", "_semaphore")

    @property
    def tui(self) -> ScrapingUI:
        return self.manager.scrape_mapper.tui

    @property
    def slots(self) -> int | None:
        return self._slots

    @slots.setter
    def slots(self, new_limit: int | None) -> None:
        if not (self._semaphore._waiters is None and self._semaphore._value == self._slots):
            raise RuntimeError("Can't change download slots. Downloader is already in use")
        self._set_capacity_limit(new_limit)

    def _set_capacity_limit(self, slots: int | None) -> None:
        if slots is not None and slots < 1:
            raise ValueError("slots has to be >=1 or None (unlimited)")
        upper_limit = self.config.downloads.concurrency_per_domain
        self._slots = min(slots or upper_limit, upper_limit)
        self._semaphore = asyncio.Semaphore(self._slots)
        self.capacity.limit = min(self._slots * 10, 50)

    @property
    def client(self) -> DownloadClient:
        return self.manager.download_client

    @error_handling_wrapper
    async def __download_w_retries(self, media_item: MediaItem) -> bool:
        while True:
            try:
                return bool(await self.__download_file(media_item))

            except DownloadError as e:
                if not self.SUPPORTS_RETRIES or not e.retry or media_item.attempts >= self.config.downloads.attempts:
                    raise

                logger.error(f"{self.log_prefix} failed: {media_item.url} with error: {e!s}")
                logger.info(
                    "Retrying %s: %s, attempt: %s",
                    self.log_prefix.lower(),
                    media_item.url,
                    media_item.attempts + 1,
                )

    async def _check_skip_by_config(self, media_item: MediaItem) -> None:
        if not _is_allowed_filetype(media_item, self.config):
            raise RestrictedFiletypeError(origin=media_item)
        if not _is_allowed_date_range(media_item, self.config):
            raise RestrictedDateRangeError(origin=media_item)
        if not await storage.has_sufficient_space(media_item.download_folder):
            raise InsufficientFreeSpaceError(media_item)
        if await filter_by_duration(media_item, self.config):
            await self.manager.database.history.add_duration(media_item.domain, media_item)
            raise DurationError(origin=media_item)

    async def _download(self, media_item: MediaItem) -> bool:
        if not media_item.is_segment:
            logger.info(f"{self.log_prefix} starting: {media_item.url}")

        async with _exclusive_lock(media_item):
            return bool(await self.__download_w_retries(media_item))

    @contextlib.asynccontextmanager
    async def __download_context(self, media_item: MediaItem) -> AsyncGenerator[None]:
        await self.client.mark_incomplete(media_item, media_item.domain)
        if media_item.is_segment:
            yield
            return

        self.capacity.waiting += 1
        async with self.lock(media_item.real_url):
            self._processed_items.add(media_item.db_path)
            async with self.capacity.condition:
                self.capacity.condition.notify()
            self.capacity.waiting -= 1
            yield

    async def __download_file(self, media_item: MediaItem) -> bool | None:
        _check_url(media_item)
        media_item.attempts += 1
        try:
            if not media_item.is_segment:
                media_item.duration = await self.manager.database.history.get_duration(media_item.domain, media_item)
                await self._check_skip_by_config(media_item)
            downloaded = await self.client.download_file(media_item.domain, media_item)

        except SkipDownloadError as e:
            if not media_item.is_segment:
                logger.info(f"Download skipped {media_item.url}: {e}")
                self.tui.files.stats.skipped += 1

        except (DownloadError, ClientResponseError, InvalidContentTypeError):
            raise

        except (
            ConnectionResetError,
            FileNotFoundError,
            PermissionError,
            TimeoutError,
            ClientError,
            ClientConnectorError,
        ) as e:
            ui_message = getattr(e, "status", type(e).__name__)
            if media_item.partial_file and (size := await aio.get_size(media_item.partial_file)):
                if self._current_attempt_filesize.get(media_item.filename, 0) >= size:
                    raise DownloadError(ui_message, message=f"{self.log_prefix} failed", retry=True) from None

                self._current_attempt_filesize[media_item.filename] = size
                raise DownloadError(status=999, message="Download timeout reached, retrying", retry=True) from None

            raise DownloadError(ui_message, str(e), retry=True) from e

        else:
            if downloaded:
                await aio.chmod(media_item.path, 0o666)
            return downloaded

    @contextlib.asynccontextmanager
    async def lock(self, url: AbsoluteHttpURL) -> AsyncGenerator[None]:
        server_lock = self._server_locks[url.host] if self.use_server_lock else _NULL_CONTEXT
        async with (
            server_lock,
            self._semaphore,
            self.manager.http_client.limiter.downloads,
        ):
            yield

    async def __skip_by_duration(self, media_item: MediaItem) -> bool:
        proceed = not await filter_by_duration(media_item, self.config)
        await self.manager.database.history.add_duration(media_item.domain, media_item)
        if not proceed:
            logger.info(f"Download skipped {media_item.url} due to runtime restrictions")
            await aio.unlink(media_item.path, missing_ok=True)
            await self.client.mark_incomplete(media_item, media_item.domain)
            self.tui.files.stats.skipped += 1
        return not proceed

    async def _prepare_multi_stream_output(self, media_item: MediaItem) -> None:
        media_item.download_folder = resolve_download_dir(media_item.download_folder, self.config)
        media_item.path = media_item.download_folder / media_item.filename
        media_item.download_filename = media_item.path.name
        await self.manager.database.history.add_download_filename(media_item.domain, media_item)

    @error_handling_wrapper
    async def run(self, media_item: MediaItem, streams: Rendition | MuxVideo | None = None) -> None:
        if media_item.db_path in self._processed_items and not self.config.ignore_history:
            return

        if streams is not None:
            assert ffmpeg.is_installed()

        async with self.__download_context(media_item):
            match streams:
                case None:
                    await self._file(media_item)
                case Rendition():
                    await self._hls(media_item, streams)
                case MuxVideo():
                    await self._mux(media_item, streams)
                case _:  # pyright: ignore[reportUnnecessaryComparison]
                    raise ValueError(f"Unsupported streams: {streams!r}")

        if media_item.downloaded:
            await self._compute_hashes(media_item)

    async def _file(self, media_item: MediaItem) -> None:
        if not await self._download(media_item):
            return

        await self.__finish_download(media_item)

    async def _mux(self, media_item: MediaItem, mux: MuxVideo) -> None:
        await self._prepare_multi_stream_output(media_item)
        p_name = Path(media_item.filename)

        def create_stream_item(name: str, url: AbsoluteHttpURL) -> MediaItem:
            filename = p_name.with_suffix(f".{name}{constants.TempExt.PART}").name
            seg_item = media_item.as_segment(filename, url)
            seg_item.extra_info["MUX_STREAM"] = True
            return seg_item

        logger.info(f"{self.log_prefix} starting (multistream video): {media_item.url}\n %s", mux.__json__())
        audio, video = create_stream_item("audio", mux.audio), create_stream_item("video", mux.video)
        results = await aio.map(self._download, (audio, video), task_limit=None)
        if not all(results):
            msg = f"Download of some streams failed. {dict(zip(('audio', 'video'), results, strict=True))}"
            raise DownloadError("Mux Download Error", msg)

        streams = hls.Streams(video.path, audio.path, None)
        await _merge_streams(media_item, streams)
        await self.__finish_download(media_item)

    async def _hls(self, media_item: MediaItem, rendition: Rendition) -> None:
        await self._prepare_multi_stream_output(media_item)
        with self.tui.downloads.download_hls(
            media_item.filename,
            media_item.domain,
            segments=sum(m.total_segments for m in rendition if m is not None),
            url=media_item.url,
        ):
            streams = await hls.download(media_item, rendition, self._download, self.client.http_client)
            await _merge_streams(media_item, streams)
            await _fixup_video(media_item)
            await self.__finish_download(media_item)

    async def __finish_download(self, media_item: MediaItem) -> None:
        assert not media_item.is_segment
        media_item.downloaded = True
        if await self.__skip_by_duration(media_item):
            media_item.downloaded = False
            return

        await _set_mtime(media_item, self.config)
        self.tui.files.stats.completed += 1
        logger.info(f"Download finished: {media_item.url}")
        await self.client.mark_completed(media_item, media_item.domain)

    async def _compute_hashes(self, media_item: MediaItem) -> None:
        # TODO: move this to the scrape_mapper as a post-download task
        if self.config.hashing.mode is not constants.HashMode.IN_PLACE:
            return
        try:
            await compute_in_place_hash(self.manager.hasher, media_item)
        except Exception:
            logger.exception("Unable to compute hashes of '%s'", media_item.path)
        finally:
            self.manager.add_completed(media_item)


async def _merge_streams(media_item: MediaItem, streams: hls.Streams) -> None:
    if not streams.audio:
        await aio.move(streams.video, media_item.path)
        return

    # TODO: add remux method to create an mkv file instead of mp4
    # Subtitles format may be incompatible with mp4 and they will be silently dropped by ffmpeg
    # so we leave them as independent files for now
    with show_msg(f"Merging {media_item.path.name}"):
        logger.debug("Merging audio and video stream for '%s' (%s)", media_item.path.name, media_item.real_url)
        result = await ffmpeg.merge(streams.video, streams.audio, media_item.path)

    if not result.success:
        raise DownloadError("FFmpeg Concat Error", result.stderr, media_item)


async def _fixup_video(media_item: MediaItem) -> None:
    if not env.FFMPEG_FIX_HLS:
        return

    with show_msg(f"Optimizing {media_item.path.name}"):
        logger.debug("Fixing MP4 container with ffmpeg: '%s' (%s)", media_item.path, media_item.real_url)
        result = await ffmpeg.optimize(media_item.path)

    if not result.success:
        raise DownloadError("FFmpeg Fixup Error", result.stderr, media_item)


def _is_allowed_filetype(media_item: MediaItem, config: Config) -> bool:
    filters = config.filters.files
    ext = media_item.ext.lower()

    for is_allowed, valid_exts in [
        (filters.images, constants.FileExt.IMAGE),
        (filters.videos, constants.FileExt.VIDEO),
        (filters.audio, constants.FileExt.AUDIO),
    ]:
        if ext in valid_exts:
            return is_allowed

    return filters.non_media


def _is_allowed_date_range(media_item: MediaItem, config: Config) -> bool:
    if not media_item.uploaded_at_date:
        return True

    return _filter_by_date(media_item.uploaded_at_date, config)


def _filter_by_date(item_datetime: datetime.datetime, config: Config) -> bool:
    item_date = item_datetime.date()
    filters = config.filters

    if filters.before and item_date > filters.before:
        return False
    return not (filters.after and item_date < filters.after)


async def _set_mtime(media_item: MediaItem, config: Config) -> None:
    if not config.mtime:
        return

    if not media_item.uploaded_at:
        logger.warning(f"Unable to parse upload date for {media_item.url}, using current datetime as file datetime")
        return

    # 1. try setting creation date
    await dates.set_creation_time(media_item.path, media_item.uploaded_at)

    # 2. try setting modification and access date
    try:
        await asyncio.to_thread(os.utime, media_item.path, (media_item.uploaded_at, media_item.uploaded_at))
    except OSError:
        pass


def _check_url(media_item: MediaItem) -> None:
    url_as_str = str(media_item.url)
    if url_as_str in _KNOWN_BAD_URLS:
        raise DownloadError(_KNOWN_BAD_URLS[url_as_str])
