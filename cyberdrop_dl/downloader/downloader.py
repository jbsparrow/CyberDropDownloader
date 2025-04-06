from __future__ import annotations

import asyncio
import re
from dataclasses import field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from aiohttp import ClientConnectorError, ClientError, ClientResponseError
from filedate import File

from cyberdrop_dl.clients.errors import (
    DownloadError,
    DurationError,
    ErrorLogMessage,
    InvalidContentTypeError,
    RestrictedFiletypeError,
)
from cyberdrop_dl.utils.data_enums_classes.url_objects import HlsSegment, MediaItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Generator, Iterable

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


def with_limiter(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(self: Downloader, *args, **kwargs) -> Any:
        media_item = args[0]
        async with self.limiter(media_item):
            return await func(self, *args, **kwargs)

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

    @contextlib.asynccontextmanager
    async def limiter(self, media_item: MediaItem):
        await self.manager.states.RUNNING.wait()
        self.waiting_items += 1
        media_item.current_attempt = 0
        await self.client.mark_incomplete(media_item, self.domain)
        self.update_queued_files()
        async with self._semaphore:
            await self.manager.states.RUNNING.wait()
            self.waiting_items -= 1
            self.processed_items.add(media_item.url.path)
            self.update_queued_files(increase_total=False)
            async with self.manager.client_manager.download_session_limit:
                try:
                    log(f"{self.log_prefix} starting: {media_item.url}", 20)
                    async with self.manager.download_manager.file_locks.get_lock(media_item):
                        yield
                finally:
                    pass

    def was_processed_before(self, media_item: MediaItem) -> bool:
        if (
            media_item.url.path in self.processed_items
            and not self.manager.config_manager.settings_data.runtime_options.ignore_history
        ):
            return True
        return False

    @with_limiter
    async def run(self, media_item: MediaItem) -> bool:
        """Runs the download loop."""
        if self.was_processed_before(media_item):
            return False
        return bool(await self.download(media_item))

    @error_handling_wrapper
    @with_limiter
    async def download_hls(self, media_item: MediaItem, m3u8_content: str) -> None:
        if self.was_processed_before(media_item):
            return

        assert media_item.debrid_link is not None
        if not self.manager.ffmpeg.is_available:
            raise DownloadError("FFmpeg Error", "FFmpeg is required for HLS downloads but is not available", media_item)

        segment_paths: set[Path] = set()
        media_item.complete_file = s = media_item.download_folder / media_item.filename
        segments_folder = s.with_suffix(".temp")

        def create_segments() -> Generator[HlsSegment]:
            last_segment = ""

            def get_segment_names() -> Generator[str]:
                nonlocal last_segment
                m3u8_lines = m3u8_content.splitlines()

                def get_valid_segment_lines(lines: Iterable[str]):
                    for line in lines:
                        segment_name = line.strip()
                        if segment_name or not segment_name.startswith("#"):
                            yield segment_name

                for segment in get_valid_segment_lines(reversed(m3u8_lines)):
                    last_segment = segment
                    break

                yield from get_valid_segment_lines(m3u8_lines)

            segment_names = get_segment_names()
            last_segment_index = re.sub(r"\D", "", last_segment)
            padding = max(5, len(last_segment_index))

            assert media_item.debrid_link is not None
            for index, name in enumerate(segment_names, 1):
                url = media_item.debrid_link / name
                custom_name = f"{index:0{padding}d}.cdl_hsl"
                yield HlsSegment(name, custom_name, url)

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

            async def download_segment():
                await self.download(seg_media_item)
                # download will return False if the file already exists (ex: downloaded in a previous run)
                # We have to manually check if the segment exists after the download
                segment_paths.add(seg_media_item.complete_file)
                await asyncio.to_thread(seg_media_item.complete_file.is_file)

            return download_segment()

        results = await asyncio.gather(*(make_download_task(segment) for segment in create_segments()))
        n_segmets = len(results)
        n_successful = sum(1 for r in results if r)

        if n_successful != n_segmets:
            msg = f"Download of some segments failed. Successful: {n_successful:,}/{n_segmets:,} "
            raise DownloadError("HLS Seg Error", msg, media_item)

        ffmpeg_result = await self.manager.ffmpeg.concat(*sorted(segment_paths), output_file=media_item.complete_file)

        if not ffmpeg_result.success:
            raise DownloadError("FFmpeg Concat Error", ffmpeg_result.stderr, media_item)

        await self.client.process_completed(media_item, self.domain)
        await self.client.handle_media_item_completion(media_item, downloaded=ffmpeg_result.success)
        self.finalize_download(media_item, ffmpeg_result.success)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def check_file_can_download(self, media_item: MediaItem) -> None:
        """Checks if the file can be downloaded."""
        await self.manager.storage_manager.check_free_space(media_item)
        if not self.manager.download_manager.check_allowed_filetype(media_item):
            raise RestrictedFiletypeError(origin=media_item)
        if not self.manager.download_manager.pre_check_duration(media_item):
            raise DurationError(origin=media_item)

    def finalize_download(self, media_item: MediaItem, downloaded: bool) -> None:
        if downloaded:
            Path.chmod(media_item.complete_file, 0o666)
            self.set_file_datetime(media_item)
            self.manager.progress_manager.download_progress.add_completed()
            log(f"Download finished: {media_item.url}", 20)
        self.attempt_task_removal(media_item)

    def set_file_datetime(self, media_item: MediaItem, complete_file: Path | None = None) -> None:
        """Sets the file's datetime."""
        if self.manager.config_manager.settings_data.download_options.disable_file_timestamps:
            return
        if not media_item.datetime:
            log(f"Unable to parse upload date for {media_item.url}, using current datetime as file datetime", 30)
            return

        complete_file = complete_file or media_item.complete_file
        file = File(str(complete_file))
        file.set(*(media_item.datetime,) * 3)  # type: ignore

    def attempt_task_removal(self, media_item: MediaItem) -> None:
        """Attempts to remove the task from the progress bar."""
        if media_item.task_id is not None:
            try:
                self.manager.progress_manager.file_progress.remove_task(media_item.task_id)
            except ValueError:
                pass

            media_item.set_task_id(None)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

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
            self.finalize_download(media_item, downloaded)
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
