from __future__ import annotations

import asyncio
import contextlib
from dataclasses import Field, field
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
from filedate import File

from cyberdrop_dl.clients.download_client import is_4xx_client_error
from cyberdrop_dl.clients.errors import CDLBaseError, DownloadError, InsufficientFreeSpaceError, RestrictedFiletypeError
from cyberdrop_dl.managers.real_debrid.errors import RealDebridError
from cyberdrop_dl.utils.constants import CustomHTTPStatus
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.clients.download_client import DownloadClient
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem


def retry(func: Callable) -> None:
    """This function is a wrapper that handles retrying for failed downloads."""

    @wraps(func)
    async def wrapper(self: Downloader, *args, **kwargs) -> None:
        media_item: MediaItem = args[0]
        while True:
            origin = exc_info = None
            try:
                return await func(self, *args, **kwargs)
            except DownloadError as e:
                self.attempt_task_removal(media_item)

                max_attempts = self.manager.config_manager.global_settings_data["Rate_Limiting_Options"][
                    "download_attempts"
                ]
                if self.manager.config_manager.settings_data["Download_Options"]["disable_download_attempt_limit"]:
                    max_attempts = 1

                if e.status != 999:
                    media_item.current_attempt += 1

                log_message = f"with status {e.status} and message: {e.message}"

                log(f"{self.log_prefix} failed: {media_item.url} {log_message}", 40)

                if media_item.current_attempt >= max_attempts:
                    self.manager.progress_manager.download_stats_progress.add_failure(e.ui_message)
                    await self.manager.log_manager.write_download_error_log(
                        media_item.url,
                        e.message,
                        media_item.referer,
                    )
                    self.manager.progress_manager.download_progress.add_failed()
                    break

                retrying_message = f"Retrying {self.log_prefix.lower()}: {media_item.url} ,retry attempt: {media_item.current_attempt + 1}"
                log(retrying_message, 20)
                continue

            except CDLBaseError as e:
                log_message = log_message_short = e.message
                ui_message = e.ui_message
                origin = e.origin

            except RealDebridError as e:
                log_message = log_message_short = f"RealDebridError - {e.error}"
                ui_message = f"RD - {e.error}"

            except Exception as e:
                exc_info = e
                log_message = str(e)
                log_message_short = "See Log for Details"
                ui_message = "Unknown"

                status = getattr(e, "status", None)
                message = getattr(e, "message", None)
                if status and message:
                    log_message = log_message_short = ui_message = f"{status} - {message}"

            failed_message = f"{self.log_prefix} failed: {media_item.url} with error: {log_message}"
            log(failed_message, 40, exc_info=exc_info)
            self.attempt_task_removal(media_item)
            await self.manager.log_manager.write_download_error_log(media_item.url, log_message_short, origin)
            self.manager.progress_manager.download_stats_progress.add_failure(ui_message)
            self.manager.progress_manager.download_progress.add_failed()
            break

    return wrapper


class Downloader:
    def __init__(self, manager: Manager, domain: str) -> None:
        self.manager: Manager = manager
        self.domain: str = domain

        self.client: DownloadClient = field(init=False)

        self._file_lock = manager.download_manager.file_lock
        self._semaphore: asyncio.Semaphore = field(init=False)

        self._additional_headers = {}

        self.processed_items: list = []
        self.waiting_items = 0
        self._current_attempt_filesize = {}
        self.log_prefix = "Download attempt (unsupported domain)" if domain == "no_crawler" else "Download"

    def startup(self) -> None:
        """Starts the downloader."""
        self.client = self.manager.client_manager.downloader_session
        self._semaphore = asyncio.Semaphore(self.manager.download_manager.get_download_limit(self.domain))

        self.manager.path_manager.download_dir.mkdir(parents=True, exist_ok=True)
        if self.manager.config_manager.settings_data["Sorting"]["sort_downloads"]:
            self.manager.path_manager.sorted_dir.mkdir(parents=True, exist_ok=True)

    async def run(self, media_item: MediaItem) -> None:
        """Runs the download loop."""
        self.waiting_items += 1
        media_item.current_attempt = 0

        await self._semaphore.acquire()
        self.waiting_items -= 1
        if media_item.url.path not in self.processed_items:
            self.processed_items.append(media_item.url.path)
            self.manager.progress_manager.download_progress.update_total()

            log(f"{self.log_prefix} starting: {media_item.url}", 20)
            async with self.manager.client_manager.download_session_limit:
                try:
                    if isinstance(media_item.file_lock_reference_name, Field):
                        media_item.file_lock_reference_name = media_item.filename
                    await self._file_lock.check_lock(media_item.file_lock_reference_name)
                    await self.download(media_item)
                except Exception as e:
                    log(f"{self.log_prefix} failed: {media_item.url} with error {e}", 40, exc_info=True)
                    self.manager.progress_manager.download_stats_progress.add_failure("Unknown")
                    self.manager.progress_manager.download_progress.add_failed()
                else:
                    log(f"{self.log_prefix} finished: {media_item.url}", 20)
                finally:
                    await self._file_lock.release_lock(media_item.file_lock_reference_name)
        self._semaphore.release()

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def check_file_can_download(self, media_item: MediaItem) -> None:
        """Checks if the file can be downloaded."""
        if not self.manager.download_manager.check_free_space(media_item.download_folder):
            raise InsufficientFreeSpaceError(origin=media_item)
        if not self.manager.download_manager.check_allowed_filetype(media_item):
            raise RestrictedFiletypeError(origin=media_item)

    def set_file_datetime(self, media_item: MediaItem, complete_file: Path) -> None:
        """Sets the file's datetime."""
        if self.manager.config_manager.settings_data["Download_Options"]["disable_file_timestamps"]:
            return
        if not isinstance(media_item.datetime, Field):
            file = File(str(complete_file))
            file.set(
                created=media_item.datetime,
                modified=media_item.datetime,
                accessed=media_item.datetime,
            )

    def attempt_task_removal(self, media_item: MediaItem) -> None:
        """Attempts to remove the task from the progress bar."""
        if not isinstance(media_item.task_id, Field):
            with contextlib.suppress(ValueError):
                self.manager.progress_manager.file_progress.remove_file(media_item.task_id)
        media_item.task_id = field(init=False)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @retry
    async def download(self, media_item: MediaItem) -> None:
        """Downloads the media item."""
        origin = media_item.referer
        try:
            if not isinstance(media_item.current_attempt, int):
                media_item.current_attempt = 1

            self.check_file_can_download(media_item)
            downloaded = await self.client.download_file(self.manager, self.domain, media_item)
            if downloaded:
                Path.chmod(media_item.complete_file, 0o666)
                self.set_file_datetime(media_item, media_item.complete_file)
                self.attempt_task_removal(media_item)
                self.manager.progress_manager.download_progress.add_completed()

        except RestrictedFiletypeError:
            self.manager.progress_manager.download_progress.add_skipped()
            self.attempt_task_removal(media_item)

        except (DownloadError, aiohttp.ClientResponseError) as e:
            ui_message = getattr(e, "ui_message", e.status)
            log_message_short = log_message = f"{e.status} - {e.message}"
            log(f"{self.log_prefix} failed: {media_item.url} with error: {log_message}", 40)
            await self.manager.log_manager.write_download_error_log(media_item.url, log_message_short, origin)
            self.manager.progress_manager.download_stats_progress.add_failure(ui_message)
            self.manager.progress_manager.download_progress.add_failed()
            self.attempt_task_removal(media_item)

        except (
            aiohttp.ClientPayloadError,
            aiohttp.ClientOSError,
            ConnectionResetError,
            FileNotFoundError,
            PermissionError,
            aiohttp.ServerDisconnectedError,
            TimeoutError,
            aiohttp.ServerTimeoutError,
        ) as e:
            ui_message = getattr(e, "status", type(e).__name__)
            if isinstance(media_item.partial_file, Path) and media_item.partial_file.is_file():
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
        return any(
            (
                is_4xx_client_error(status) and status != HTTPStatus.TOO_MANY_REQUESTS,
                status in (HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY, CustomHTTPStatus.WEB_SERVER_IS_DOWN),
            ),
        )
