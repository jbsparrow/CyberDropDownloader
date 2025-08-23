from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import field
from datetime import datetime
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from aiohttp import ClientConnectorError, ClientError, ClientResponseError

from cyberdrop_dl.constants import CustomHTTPStatus
from cyberdrop_dl.data_structures.url_objects import HlsSegment, MediaItem
from cyberdrop_dl.exceptions import (
    DownloadError,
    DurationError,
    ErrorLogMessage,
    InvalidContentTypeError,
    RestrictedFiletypeError,
    TooManyCrawlerErrors,
)
from cyberdrop_dl.utils import ffmpeg
from cyberdrop_dl.utils.database.tables.history_table import get_db_path
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_size_or_none, parse_url

# Windows epoch is January 1, 1601. Unix epoch is January 1, 1970
WIN_EPOCH_OFFSET = 116444736e9
MAC_OS_SET_FILE = None


# Try to import win32con for Windows constants, fallback to hardcoded values if unavailable
try:
    import win32con

    FILE_WRITE_ATTRIBUTES = 256
    OPEN_EXISTING = win32con.OPEN_EXISTING
    FILE_ATTRIBUTE_NORMAL = win32con.FILE_ATTRIBUTE_NORMAL
    FILE_FLAG_BACKUP_SEMANTICS = win32con.FILE_FLAG_BACKUP_SEMANTICS
except ImportError:
    FILE_WRITE_ATTRIBUTES = 256
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 128
    FILE_FLAG_BACKUP_SEMANTICS = 33554432

if sys.platform == "win32":
    from ctypes import byref, windll, wintypes


elif sys.platform == "darwin":
    # SetFile is non standard in macOS. Only users that have xcode installed will have SetFile
    MAC_OS_SET_FILE = shutil.which("SetFile")


if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Generator

    from cyberdrop_dl.clients.download_client import DownloadClient
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.m3u8 import M3U8, RenditionGroup

P = ParamSpec("P")
R = TypeVar("R")

KNOWN_BAD_URLS = {
    "https://i.imgur.com/removed.png": 404,
    "https://saint2.su/assets/notfound.gif": 404,
    "https://bnkr.b-cdn.net/maintenance-vid.mp4": 503,
    "https://bnkr.b-cdn.net/maintenance.mp4": 503,
    "https://c.bunkr-cache.se/maintenance-vid.mp4": 503,
    "https://c.bunkr-cache.se/maintenance.jpg": 503,
}


def retry(func: Callable[P, Coroutine[None, None, R]]) -> Callable[P, Coroutine[None, None, R]]:
    """This function is a wrapper that handles retrying for failed downloads."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> R:
        self: Downloader = args[0]
        media_item: MediaItem = args[1]
        while True:
            try:
                return await func(*args, **kwargs)
            except DownloadError as e:
                if not e.retry:
                    raise

                self.attempt_task_removal(media_item)
                if e.status != 999:
                    media_item.current_attempt += 1

                log(f"{self.log_prefix} failed: {media_item.url} with error: {e!s}", 40)
                if media_item.current_attempt >= self.max_attempts:
                    raise

                retry_msg = f"Retrying {self.log_prefix.lower()}: {media_item.url} , retry attempt: {media_item.current_attempt + 1}"
                log(retry_msg, 20)

    return wrapper


GENERIC_CRAWLERS = ".", "no_crawler"


class Downloader:
    def __init__(self, manager: Manager, domain: str) -> None:
        self.manager: Manager = manager
        self.domain: str = domain

        self.client: DownloadClient = field(init=False)
        self.log_prefix = "Download attempt (unsupported domain)" if domain in GENERIC_CRAWLERS else "Download"
        self.processed_items: set[str] = set()
        self.waiting_items = 0

        self._additional_headers = {}
        self._current_attempt_filesize = {}
        self._file_lock_vault = manager.download_manager.file_locks
        self._ignore_history = manager.config_manager.settings_data.runtime_options.ignore_history
        self._semaphore: asyncio.Semaphore = field(init=False)

    @property
    def max_attempts(self):
        if self.manager.config_manager.settings_data.download_options.disable_download_attempt_limit:
            return 1
        return self.manager.config_manager.global_settings_data.rate_limiting_options.download_attempts

    def startup(self) -> None:
        """Starts the downloader."""
        self.client = self.manager.client_manager.downloader_session
        self._semaphore = asyncio.Semaphore(self.manager.download_manager.get_download_limit(self.domain))

        self.manager.path_manager.download_folder.mkdir(parents=True, exist_ok=True)
        if self.manager.config_manager.settings_data.sorting.sort_downloads:
            self.manager.path_manager.sorted_folder.mkdir(parents=True, exist_ok=True)

    def update_queued_files(self, increase_total: bool = True):
        queued_files = self.manager.progress_manager.file_progress.get_queue_length()
        self.manager.progress_manager.download_progress.update_queued(queued_files)
        self.manager.progress_manager.download_progress.update_total(increase_total)

    async def run(self, media_item: MediaItem) -> bool:
        """Runs the download loop."""

        if media_item.url.path in self.processed_items and not self._ignore_history:
            return False

        await self.manager.states.RUNNING.wait()
        self.waiting_items += 1
        media_item.current_attempt = 0
        await self.client.mark_incomplete(media_item, self.domain)
        if not media_item.is_segment:
            self.update_queued_files()
        async with self._semaphore:
            await self.manager.states.RUNNING.wait()
            self.waiting_items -= 1
            self.processed_items.add(get_db_path(media_item.url, self.domain))
            self.update_queued_files(increase_total=False)
            async with self.manager.client_manager.download_session_limit:
                return await self.start_download(media_item)

    @error_handling_wrapper
    async def download_hls(self, media_item: MediaItem, m3u8_group: RenditionGroup) -> None:
        await self.client.mark_incomplete(media_item, self.domain)
        try:
            ffmpeg.check_is_available()
        except RuntimeError as e:
            msg = f"{e} - ffmpeg and ffprobe are required for HLS downloads"
            raise DownloadError("FFmpeg Error", msg, media_item) from None

        media_item.complete_file = media_item.download_folder / media_item.filename
        self.update_queued_files()
        task_id = self.manager.progress_manager.file_progress.add_task(domain=self.domain, filename=media_item.filename)
        media_item.set_task_id(task_id)
        video, audio, subtitles = await self._process_m3u8_rendition_group(media_item, m3u8_group)
        if not subtitles and not audio:
            await asyncio.to_thread(video.rename, media_item.complete_file)
        else:
            parts = [part for part in (video, audio, subtitles) if part]
            ffmpeg_result = await ffmpeg.merge(parts, media_item.complete_file)

            if not ffmpeg_result.success:
                raise DownloadError("FFmpeg Concat Error", ffmpeg_result.stderr, media_item)

        await self.client.process_completed(media_item, self.domain)
        await self.client.handle_media_item_completion(media_item, downloaded=True)
        await self.finalize_download(media_item, downloaded=True)

    async def _process_m3u8_rendition_group(
        self, media_item: MediaItem, m3u8_group: RenditionGroup
    ) -> tuple[Path, Path | None, Path | None]:
        results: list[Path | None] = []
        for media_type, m3u8 in zip(("video", "audio", "subtitles"), m3u8_group, strict=True):
            if not m3u8:
                results.append(None)
                continue

            download_folder = media_item.complete_file.with_suffix(".cdl_hls") / media_type
            items, tasks = self._make_hls_tasks(media_item, m3u8, download_folder)
            tasks_results = await asyncio.gather(*tasks)
            n_segmets = len(tasks_results)
            n_successful = sum(1 for r in tasks_results if r)

            if n_successful != n_segmets:
                msg = f"Download of some segments failed. Successful: {n_successful:,}/{n_segmets:,} "
                raise DownloadError("HLS Seg Error", msg, media_item)

            seg_paths = [item.complete_file for item in items if item.complete_file]
            output = media_item.complete_file.with_suffix(f".{media_type}.ts")
            ffmpeg_result = await ffmpeg.concat(seg_paths, output)
            if not ffmpeg_result.success:
                raise DownloadError("FFmpeg Concat Error", ffmpeg_result.stderr, media_item)
            results.append(output)

        video, audio, subtitles = results
        assert video
        return video, audio, subtitles

    def _make_hls_tasks(
        self, media_item: MediaItem, m3u8: M3U8, download_folder: Path
    ) -> tuple[list[MediaItem], list[Coroutine]]:
        seg_media_items: list[MediaItem] = []
        padding = max(5, len(str(len(m3u8.segments))))
        semaphore_hls = asyncio.Semaphore(10)

        def create_segments() -> Generator[HlsSegment]:
            for index, segment in enumerate(m3u8.segments, 1):
                assert segment.uri
                name = f"{index:0{padding}d}.cdl_hsl"
                yield HlsSegment(segment.title, name, parse_url(segment.absolute_uri))

        def make_download_task(segment: HlsSegment) -> Coroutine:
            seg_media_item = MediaItem.from_item(
                media_item,
                segment.url,
                download_folder=download_folder,
                filename=segment.name,
                ext=media_item.ext,
                is_segment=True,
                # add_to_database=False,
                # quiet=True,
                # reference=media_item,
                # skip_hashing=True,
            )
            seg_media_items.append(seg_media_item)

            async def run() -> bool:
                async with semaphore_hls:
                    return await self.start_download(seg_media_item)

            return run()

        return seg_media_items, [make_download_task(segment) for segment in create_segments()]

    async def finalize_download(self, media_item: MediaItem, downloaded: bool) -> None:
        if downloaded:
            await asyncio.to_thread(Path.chmod, media_item.complete_file, 0o666)
            await self.set_file_datetime(media_item, media_item.complete_file)
        self.attempt_task_removal(media_item)
        self.manager.progress_manager.download_progress.add_completed()
        log(f"Download finished: {media_item.url}", 20)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def check_file_can_download(self, media_item: MediaItem) -> None:
        """Checks if the file can be downloaded."""
        await self.manager.storage_manager.check_free_space(media_item)
        if not self.manager.download_manager.check_allowed_filetype(media_item):
            raise RestrictedFiletypeError(origin=media_item)
        if not self.manager.download_manager.pre_check_duration(media_item):
            raise DurationError(origin=media_item)

    async def set_file_datetime(self, media_item: MediaItem, complete_file: Path) -> None:
        """Sets the file's datetime."""
        if self.manager.config_manager.settings_data.download_options.disable_file_timestamps:
            return
        if not media_item.datetime:
            log(f"Unable to parse upload date for {media_item.url}, using current datetime as file datetime", 30)
            return

        # TODO: Make this entire method async (run in another thread)

        # 1. try setting creation date
        try:
            if sys.platform == "win32":

                def set_win_time():
                    nano_ts: float = media_item.datetime * 1e7  # Windows uses nano seconds for dates
                    timestamp = int(nano_ts + WIN_EPOCH_OFFSET)

                    # Windows dates are 64bits, split into 2 32bits unsigned ints (dwHighDateTime , dwLowDateTime)
                    # XOR to get the date as bytes, then shift to get the first 32 bits (dwHighDateTime)
                    ctime = wintypes.FILETIME(timestamp & 0xFFFFFFFF, timestamp >> 32)
                    access_mode = FILE_WRITE_ATTRIBUTES
                    sharing_mode = 0  # Exclusive access
                    security_mode = None  # Use default security attributes
                    creation_disposition = OPEN_EXISTING

                    # FILE_FLAG_BACKUP_SEMANTICS allows access to directories
                    flags = FILE_ATTRIBUTE_NORMAL | FILE_FLAG_BACKUP_SEMANTICS
                    template_file = None

                    params = (
                        access_mode,
                        sharing_mode,
                        security_mode,
                        creation_disposition,
                        flags,
                        template_file,
                    )

                    handle = windll.kernel32.CreateFileW(str(complete_file), *params)
                    windll.kernel32.SetFileTime(
                        handle,
                        byref(ctime),  # Creation time
                        None,  # Access time
                        None,  # Modification time
                    )
                    windll.kernel32.CloseHandle(handle)

                await asyncio.to_thread(set_win_time)

            elif sys.platform == "darwin" and MAC_OS_SET_FILE:
                date_string = datetime.fromtimestamp(media_item.datetime).strftime("%m/%d/%Y %H:%M:%S")
                cmd = ["-d", date_string, complete_file]
                process = await asyncio.subprocess.create_subprocess_exec(
                    MAC_OS_SET_FILE, *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                _ = await process.wait()

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError):
            pass

        # 2. try setting modification and access date
        try:
            await asyncio.to_thread(os.utime, complete_file, (media_item.datetime, media_item.datetime))
        except OSError:
            pass

    def attempt_task_removal(self, media_item: MediaItem) -> None:
        """Attempts to remove the task from the progress bar."""
        if media_item.is_segment:
            return
        if media_item.task_id is not None:
            try:
                self.manager.progress_manager.file_progress.remove_task(media_item.task_id)
            except ValueError:
                pass

            media_item.set_task_id(None)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def start_download(self, media_item: MediaItem) -> bool:
        try:
            self.client.client_manager.check_domain_errors(self.domain)
        except TooManyCrawlerErrors:
            return False

        if not media_item.is_segment:
            log(f"{self.log_prefix} starting: {media_item.url}", 20)
        lock = self._file_lock_vault.get_lock(media_item.filename)
        async with lock:
            return bool(await self.download(media_item))

    @error_handling_wrapper
    @retry
    async def download(self, media_item: MediaItem) -> bool | None:
        """Downloads the media item."""
        url_as_str = str(media_item.url)
        if url_as_str in KNOWN_BAD_URLS:
            raise DownloadError(KNOWN_BAD_URLS[url_as_str])
        try:
            await self.manager.states.RUNNING.wait()
            self.client.client_manager.check_domain_errors(self.domain)
            media_item.current_attempt = media_item.current_attempt or 1
            if not media_item.is_segment:
                media_item.duration = await self.manager.db_manager.history_table.get_duration(self.domain, media_item)
                await self.check_file_can_download(media_item)
            downloaded = await self.client.download_file(self.manager, self.domain, media_item)
            if downloaded:
                await asyncio.to_thread(Path.chmod, media_item.complete_file, 0o666)
                if not media_item.is_segment:
                    await self.set_file_datetime(media_item, media_item.complete_file)
                    self.attempt_task_removal(media_item)
                    self.manager.progress_manager.download_progress.add_completed()
                    log(f"Download finished: {media_item.url}", 20)
            return downloaded

        except RestrictedFiletypeError:
            if not media_item.is_segment:
                log(f"Download skip {media_item.url} due to ignore_extension config ({media_item.ext})", 10)
                self.manager.progress_manager.download_progress.add_skipped()
                self.attempt_task_removal(media_item)

        except (DownloadError, ClientResponseError, InvalidContentTypeError, ClientConnectorError):
            raise

        except (
            ConnectionResetError,
            FileNotFoundError,
            PermissionError,
            TimeoutError,
            ClientError,
        ) as e:
            ui_message = getattr(e, "status", type(e).__name__)
            if size := await asyncio.to_thread(get_size_or_none, media_item.partial_file):
                if (
                    media_item.filename in self._current_attempt_filesize
                    and self._current_attempt_filesize[media_item.filename] >= size
                ):
                    raise DownloadError(ui_message, message=f"{self.log_prefix} failed", retry=True) from None
                self._current_attempt_filesize[media_item.filename] = size
                media_item.current_attempt = 0
                raise DownloadError(status=999, message="Download timeout reached, retrying", retry=True) from None

            message = str(e)
            raise DownloadError(ui_message, message, retry=True) from e

    async def write_download_error(self, media_item: MediaItem, error_log_msg: ErrorLogMessage, exc_info=None) -> None:
        self.attempt_task_removal(media_item)
        full_message = f"{self.log_prefix} Failed: {media_item.url} ({error_log_msg.main_log_msg}) \n -> Referer: {media_item.referer}"
        log(full_message, 40, exc_info=exc_info)
        self.manager.log_manager.write_download_error_log(media_item, error_log_msg.csv_log_msg)
        self.manager.progress_manager.download_stats_progress.add_failure(error_log_msg.ui_failure)
        self.manager.progress_manager.download_progress.add_failed()

    @staticmethod
    def is_failed(status: int):
        """NO USED"""
        SERVER_ERRORS = (HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY, CustomHTTPStatus.WEB_SERVER_IS_DOWN)
        return any(
            (is_4xx_client_error(status) and status != HTTPStatus.TOO_MANY_REQUESTS, status in SERVER_ERRORS),
        )


def is_4xx_client_error(status_code: int) -> bool:
    """Checks whether the HTTP status code is 4xx client error."""
    return isinstance(status_code, str) or (HTTPStatus.BAD_REQUEST <= status_code < HTTPStatus.INTERNAL_SERVER_ERROR)
