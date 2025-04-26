from __future__ import annotations

import asyncio
import re
from dataclasses import field
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from aiohttp import ClientConnectorError, ClientError, ClientResponseError
from filedate import File

from cyberdrop_dl.clients.errors import (
    DownloadError,
    DurationError,
    ErrorLogMessage,
    InvalidContentTypeError,
    RestrictedFiletypeError,
)
from cyberdrop_dl.utils.constants import CustomHTTPStatus
from cyberdrop_dl.utils.data_enums_classes.url_objects import HlsSegment, MediaItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Generator

    from cyberdrop_dl.clients.download_client import DownloadClient
    from cyberdrop_dl.managers.manager import Manager

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
        self.processed_items: set = set()
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
            self.processed_items.add(media_item.url.path)
            self.update_queued_files(increase_total=False)
            async with self.manager.client_manager.download_session_limit:
                return await self.start_download(media_item)

    @error_handling_wrapper
    async def download_hls(self, media_item: MediaItem, m3u8_content: str) -> None:
        assert media_item.debrid_link
        await self.client.mark_incomplete(media_item, self.domain)
        if not self.manager.ffmpeg.is_available:
            raise DownloadError("FFmpeg Error", "FFmpeg is required for HLS downloads but is not available", media_item)

        seg_media_items: list[MediaItem] = []
        media_item.complete_file = s = media_item.download_folder / media_item.filename
        segments_folder = s.with_suffix(".cdl_hls")
        m3u8_lines = m3u8_content.splitlines()

        def create_segments() -> Generator[HlsSegment]:
            def get_last_segment_line() -> str:
                for line in reversed(m3u8_lines):
                    if not line.startswith("#"):
                        return line.strip()
                raise DownloadError("Invalid M3U8", "Inable to parse m3u8 content", media_item)

            def get_segment_lines() -> Generator[str]:
                for line in m3u8_lines:
                    segment = line.strip()
                    if not segment or segment.startswith("#"):
                        continue
                    yield segment

            last_segment_part = get_last_segment_line()
            last_index_str = re.sub(r"\D", "", last_segment_part)
            padding = max(5, len(last_index_str))
            parts = get_segment_lines()
            for index, part in enumerate(parts, 1):
                url = media_item.debrid_link / part  # type: ignore
                name = f"{index:0{padding}d}.cdl_hsl"
                yield HlsSegment(part, name, url)

        def make_download_task(segment: HlsSegment):
            seg_media_item = MediaItem(
                segment.url,
                media_item,
                segments_folder,
                segment.name,
                ext=media_item.ext,
                is_segment=True,
                # add_to_database=False,
                # quiet=True,
                # reference=media_item,
                # skip_hashing=True,
            )
            seg_media_items.append(seg_media_item)
            return self.run(seg_media_item)

        self.update_queued_files()
        results = await asyncio.gather(*(make_download_task(s) for s in create_segments()))
        n_segmets = len(results)
        n_successful = sum(1 for r in results if r)

        if n_successful != n_segmets:
            msg = f"Download of some segments failed. Successful: {n_successful:,}/{n_segmets:,} "
            raise DownloadError("HLS Seg Error", msg, media_item)

        seg_paths = [m.complete_file for m in seg_media_items if m.complete_file]
        ffmpeg_result = await self.manager.ffmpeg.concat(*seg_paths, output_file=media_item.complete_file)

        if not ffmpeg_result.success:
            raise DownloadError("FFmpeg Concat Error", ffmpeg_result.stderr, media_item)

        await self.client.process_completed(media_item, self.domain)
        await self.client.handle_media_item_completion(media_item, downloaded=ffmpeg_result.success)
        self.finalize_download(media_item, ffmpeg_result.success)

    def finalize_download(self, media_item: MediaItem, downloaded: bool) -> None:
        if downloaded:
            Path.chmod(media_item.complete_file, 0o666)
            self.set_file_datetime(media_item, media_item.complete_file)
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

    def set_file_datetime(self, media_item: MediaItem, complete_file: Path) -> None:
        """Sets the file's datetime."""
        if self.manager.config_manager.settings_data.download_options.disable_file_timestamps:
            return
        if not media_item.datetime:
            log(f"Unable to parse upload date for {media_item.url}, using current datetime as file datetime", 30)
            return

        file = File(str(complete_file))
        file.set(
            created=media_item.datetime,
            modified=media_item.datetime,
            accessed=media_item.datetime,
        )

    def attempt_task_removal(self, media_item: MediaItem) -> None:
        """Attempts to remove the task from the progress bar."""
        if media_item.task_id is not None:
            try:
                self.manager.progress_manager.file_progress.remove_task(media_item.task_id)
            except ValueError:
                pass

            media_item.set_task_id(None)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def start_download(self, media_item: MediaItem) -> bool:
        if not media_item.is_segment:
            log(f"{self.log_prefix} starting: {media_item.url}", 20)
        if not media_item.file_lock_reference_name:
            media_item.file_lock_reference_name = media_item.filename
        lock = self._file_lock_vault.get_lock(media_item.file_lock_reference_name)
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
            media_item.current_attempt = media_item.current_attempt or 1
            media_item.duration = await self.manager.db_manager.history_table.get_duration(self.domain, media_item)
            await self.check_file_can_download(media_item)
            downloaded = await self.client.download_file(self.manager, self.domain, media_item)
            if downloaded:
                Path.chmod(media_item.complete_file, 0o666)
                self.set_file_datetime(media_item, media_item.complete_file)
                self.attempt_task_removal(media_item)
                self.manager.progress_manager.download_progress.add_completed()
                log(f"Download finished: {media_item.url}", 20)
            return downloaded

        except RestrictedFiletypeError:
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
            if media_item.partial_file and media_item.partial_file.is_file():
                size = media_item.partial_file.stat().st_size
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
        await self.manager.log_manager.write_download_error_log(media_item, error_log_msg.csv_log_msg)
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
