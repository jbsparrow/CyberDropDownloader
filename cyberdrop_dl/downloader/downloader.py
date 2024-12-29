from __future__ import annotations

import asyncio
import contextlib
from dataclasses import field
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientResponseError
from filedate import File

from cyberdrop_dl.clients.errors import DownloadError, InsufficientFreeSpaceError, RestrictedFiletypeError
from cyberdrop_dl.utils.constants import CustomHTTPStatus
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.clients.download_client import DownloadClient
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


def retry(func: Callable) -> None:
    """This function is a wrapper that handles retrying for failed downloads."""

    @wraps(func)
    async def wrapper(self: Downloader, *args, **kwargs) -> None:
        media_item: MediaItem = args[0]
        while True:
            try:
                return await func(self, *args, **kwargs)
            except DownloadError as e:
                self.attempt_task_removal(media_item)
                max_attempts = self.manager.config_manager.global_settings_data.rate_limiting_options.download_attempts
                if self.manager.config_manager.settings_data.download_options.disable_download_attempt_limit:
                    max_attempts = 1

                if e.status != 999:
                    media_item.current_attempt += 1

                log_message = f"with status {e.status} and message: {e.message}"
                log(f"{self.log_prefix} failed: {media_item.url} {log_message}", 40)
                if media_item.current_attempt < max_attempts:
                    retry_msg = f"Retrying {self.log_prefix.lower()}: {media_item.url} , retry attempt: {media_item.current_attempt + 1}"
                    log(retry_msg, 20)
                    continue

                self.manager.progress_manager.download_stats_progress.add_failure(e.ui_message)
                await self.manager.log_manager.write_download_error_log(media_item.url, e.message, media_item.referer)
                self.manager.progress_manager.download_progress.add_failed()
                break

    return wrapper


class Downloader:
    def __init__(self, manager: Manager, domain: str) -> None:
        self.manager: Manager = manager
        self.domain: str = domain

        self.client: DownloadClient = field(init=False)
        self.log_prefix = "Download attempt (unsupported domain)" if domain == "no_crawler" else "Download"
        self.processed_items: set = set()
        self.waiting_items = 0

        self._additional_headers = {}
        self._current_attempt_filesize = {}
        self._file_lock_vault = manager.download_manager.file_locks
        self._ignore_history = manager.config_manager.settings_data.runtime_options.ignore_history
        self._semaphore: asyncio.Semaphore = field(init=False)

    def startup(self) -> None:
        """Starts the downloader."""
        self.client = self.manager.client_manager.downloader_session
        self._semaphore = asyncio.Semaphore(self.manager.download_manager.get_download_limit(self.domain))

        self.manager.path_manager.download_folder.mkdir(parents=True, exist_ok=True)
        if self.manager.config_manager.settings_data.sorting.sort_downloads:
            self.manager.path_manager.sorted_folder.mkdir(parents=True, exist_ok=True)

    async def run(self, media_item: MediaItem) -> None:
        """Runs the download loop."""

        if media_item.url.path in self.processed_items and not self._ignore_history:
            return

        self.waiting_items += 1
        media_item.current_attempt = 0
        async with self._semaphore:
            self.waiting_items -= 1
            self.processed_items.add(media_item.url.path)
            self.manager.progress_manager.download_progress.update_total()
            async with self.manager.client_manager.download_session_limit:
                await self.start_download(media_item)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def check_file_can_download(self, media_item: MediaItem) -> None:
        """Checks if the file can be downloaded."""
        if not self.manager.download_manager.check_free_space(media_item.download_folder):
            raise InsufficientFreeSpaceError(origin=media_item)
        if not self.manager.download_manager.check_allowed_filetype(media_item):
            raise RestrictedFiletypeError(origin=media_item)

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
            with contextlib.suppress(ValueError):
                self.manager.progress_manager.file_progress.remove_file(media_item.task_id)
        media_item.task_id = None

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def start_download(self, media_item: MediaItem) -> None:
        log(f"{self.log_prefix} starting: {media_item.url}", 20)
        if not media_item.file_lock_reference_name:
            media_item.file_lock_reference_name = media_item.filename
        lock = self._file_lock_vault.get_lock(media_item.file_lock_reference_name)
        async with lock:
            await self.download(media_item)

    @error_handling_wrapper
    @retry
    async def download(self, media_item: MediaItem) -> None:
        """Downloads the media item."""
        origin = media_item.referer
        try:
            media_item.current_attempt = media_item.current_attempt or 1
            self.check_file_can_download(media_item)
            downloaded = await self.client.download_file(self.manager, self.domain, media_item)
            if downloaded:
                Path.chmod(media_item.complete_file, 0o666)
                self.set_file_datetime(media_item, media_item.complete_file)
                self.attempt_task_removal(media_item)
                self.manager.progress_manager.download_progress.add_completed()
                log(f"Download finished: {media_item.url}", 20)

        except RestrictedFiletypeError:
            log(f"Download skip {media_item.url} due to ignore_extension config ({media_item.ext})", 10)
            self.manager.progress_manager.download_progress.add_skipped()
            self.attempt_task_removal(media_item)

        except (DownloadError, ClientResponseError) as e:
            ui_message = getattr(e, "ui_message", e.status)
            log_message_short = log_message = f"{e.status} - {e.message}"
            log(f"{self.log_prefix} failed: {media_item.url} with error: {log_message}", 40)
            await self.manager.log_manager.write_download_error_log(media_item.url, log_message_short, origin)
            self.manager.progress_manager.download_stats_progress.add_failure(ui_message)
            self.manager.progress_manager.download_progress.add_failed()
            self.attempt_task_removal(media_item)

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
                    raise DownloadError(ui_message, message=f"{self.log_prefix} failed") from None
                self._current_attempt_filesize[media_item.filename] = size
                media_item.current_attempt = 0
                raise DownloadError(status=999, message="Download timeout reached, retrying") from None

            message = str(e)
            raise DownloadError(ui_message, message) from e

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
