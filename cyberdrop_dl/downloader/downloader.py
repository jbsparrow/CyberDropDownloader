from __future__ import annotations

import asyncio
import os
from dataclasses import field, Field
from functools import wraps
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
import filedate

from cyberdrop_dl.clients.download_client import is_4xx_client_error
from cyberdrop_dl.clients.errors import DownloadFailure, CDLBaseException
from cyberdrop_dl.managers.real_debrid.errors import RealDebridError
from cyberdrop_dl.utils.utilities import CustomHTTPStatus, log

if TYPE_CHECKING:
    from cyberdrop_dl.clients.download_client import DownloadClient
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem


def retry(f):
    """This function is a wrapper that handles retrying for failed downloads"""

    @wraps(f)
    async def wrapper(self: Downloader, *args, **kwargs):
        media_item: MediaItem = args[0]
        while True:
            e_origin = exc_info = None
            try:
                return await f(self, *args, **kwargs)
            except DownloadFailure as e:
                await self.attempt_task_removal(media_item)

                max_attempts = self.manager.config_manager.global_settings_data['Rate_Limiting_Options'][
                    'download_attempts']
                if self.manager.config_manager.settings_data['Download_Options']['disable_download_attempt_limit']:
                    max_attempts = 1

                if e.status != 999:
                    media_item.current_attempt += 1

                if hasattr(e, "status") and hasattr(e, "message"):
                    e_log_detail = f"with status {e.status} and message: {e.message}"
                elif hasattr(e, "status"):
                    e_log_detail = f"with status {e.status}"
                else:
                    e_log_detail = f"with error {e}"

                await log(f"{self.log_prefix} failed: {media_item.url} {e_log_detail}", 40)

                if media_item.current_attempt >= max_attempts:
                    await self.manager.progress_manager.download_stats_progress.add_failure(e.ui_message)
                    await self.manager.log_manager.write_download_error_log(media_item.url, e.message,
                                                                            media_item.referer)
                    await self.manager.progress_manager.download_progress.add_failed()
                    break

                await log(
                    f"Retrying {self.log_prefix.lower()}: {media_item.url} ,retry attempt: {media_item.current_attempt + 1}",
                    20)
                continue


            except CDLBaseException as err:
                e_log_detail = e_log_message = err.message
                e_ui_failure = err.ui_message
                e_origin = err.origin

            except RealDebridError as err:
                e_log_detail = e_log_message = f"RealDebridError - {err.error}"
                e_ui_failure = f"RD - {err.error}"

            except Exception as err:
                exc_info = True
                if hasattr(err, 'status') and hasattr(err, 'message'):
                    e_log_detail = e_log_message = e_ui_failure = f"{err.status} - {err.message}"
                else:
                    e_log_detail = str(err)
                    e_log_message = "See Log for Details"
                    e_ui_failure = "Unknown"

                await log(f"{self.log_prefix} failed: {media_item.url} with error: {e_log_detail}", 40,
                        exc_info=exc_info)

            if not exc_info:
                await log(f"{self.log_prefix} failed: {media_item.url} with error: {e_log_detail}", 40)
            await self.attempt_task_removal(media_item)
            await self.manager.log_manager.write_download_error_log(media_item.url, e_log_message, e_origin)
            await self.manager.progress_manager.download_stats_progress.add_failure(e_ui_failure)
            await self.manager.progress_manager.download_progress.add_failed()
            break

    return wrapper


class Downloader:
    def __init__(self, manager: Manager, domain: str):
        self.manager: Manager = manager
        self.domain: str = domain

        self.client: DownloadClient = field(init=False)

        self._file_lock = manager.download_manager.file_lock
        self._semaphore: asyncio.Semaphore = field(init=False)

        self._additional_headers = {}

        self.processed_items: list = []
        self.waiting_items = 0
        self._current_attempt_filesize = {}
        self.log_prefix = "Download attempt (unsupported domain)" if domain == 'no_crawler' else 'Download'

    async def startup(self) -> None:
        """Starts the downloader"""
        self.client = self.manager.client_manager.downloader_session
        self._semaphore = asyncio.Semaphore(await self.manager.download_manager.get_download_limit(self.domain))

        self.manager.path_manager.download_dir.mkdir(parents=True, exist_ok=True)
        if self.manager.config_manager.settings_data['Sorting']['sort_downloads']:
            self.manager.path_manager.sorted_dir.mkdir(parents=True, exist_ok=True)

    async def run(self, media_item: MediaItem) -> None:
        """Runs the download loop"""
        self.waiting_items += 1
        media_item.current_attempt = 0

        await self._semaphore.acquire()
        self.waiting_items -= 1
        if media_item.url.path not in self.processed_items:
            self.processed_items.append(media_item.url.path)
            await self.manager.progress_manager.download_progress.update_total()

            await log(f"{self.log_prefix} starting: {media_item.url}", 20)
            async with self.manager.client_manager.download_session_limit:
                try:
                    if isinstance(media_item.file_lock_reference_name, Field):
                        media_item.file_lock_reference_name = media_item.filename
                    await self._file_lock.check_lock(media_item.file_lock_reference_name)

                    await self.download(media_item)
                except Exception as e:
                    await log(f"{self.log_prefix} failed: {media_item.url} with error {e}", 40, exc_info=True)
                    await self.manager.progress_manager.download_stats_progress.add_failure("Unknown")
                    await self.manager.progress_manager.download_progress.add_failed()
                else:
                    await log(f"{self.log_prefix} finished: {media_item.url}", 20)
                finally:
                    await self._file_lock.release_lock(media_item.file_lock_reference_name)
        self._semaphore.release()

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def check_file_can_download(self, media_item: MediaItem) -> bool:
        """Checks if the file can be downloaded"""
        if not await self.manager.download_manager.check_free_space(media_item.download_folder):
            await log(f"{self.log_prefix} failed {media_item.url} due to insufficient free space", 10)
            return False, 0
        if not await self.manager.download_manager.check_allowed_filetype(media_item):
            await log(f"{self.log_prefix} skipped {media_item.url} due to filetype restrictions", 10)
            return False, 1
        return True, -1

    async def set_file_datetime(self, media_item: MediaItem, complete_file: Path) -> None:
        """Sets the file's datetime"""
        if self.manager.config_manager.settings_data['Download_Options']['disable_file_timestamps']:
            return
        if not isinstance(media_item.datetime, Field):
            file = filedate.File(str(complete_file))
            file.set(
                created=media_item.datetime,
                modified=media_item.datetime,
                accessed=media_item.datetime,
            )

    async def attempt_task_removal(self, media_item: MediaItem) -> None:
        """Attempts to remove the task from the progress bar"""
        if not isinstance(media_item.task_id, Field):
            try:
                await self.manager.progress_manager.file_progress.remove_file(media_item.task_id)
            except ValueError:
                pass
        media_item.task_id = field(init=False)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @retry
    async def download(self, media_item: MediaItem) -> None:
        """Downloads the media item"""
        try:
            if not isinstance(media_item.current_attempt, int):
                media_item.current_attempt = 1

            can_download, reason = await self.check_file_can_download(media_item)
            if not can_download:
                if reason == 0:
                    await self.manager.progress_manager.download_stats_progress.add_failure("Insufficient Free Space")
                    await self.manager.log_manager.write_download_error_log(media_item.url, "Insufficient Free Space",
                                                                            media_item.referer)
                    await self.manager.progress_manager.download_progress.add_failed()
                else:
                    await self.manager.progress_manager.download_progress.add_skipped()
                return

            downloaded = await self.client.download_file(self.manager, self.domain, media_item)

            if downloaded:
                os.chmod(media_item.complete_file, 0o666)
                await self.set_file_datetime(media_item, media_item.complete_file)
                await self.attempt_task_removal(media_item)
                await self.manager.progress_manager.download_progress.add_completed()

        except (aiohttp.ClientPayloadError, aiohttp.ClientOSError, aiohttp.ClientResponseError, ConnectionResetError,
                DownloadFailure, FileNotFoundError, PermissionError, aiohttp.ServerDisconnectedError,
                asyncio.TimeoutError, aiohttp.ServerTimeoutError) as err:

            e_origin = media_item.referer

            if hasattr(err, "status") and await self.is_failed(err.status):
                e_ui_failure = err.ui_message if isinstance(err, CDLBaseException) else err.status

                if hasattr(err, 'message'):
                    e_log_detail = e_log_message = f"{err.status} - {err.message}"
                else:
                    e_log_detail = str(err)
                    e_log_message = f"{err.status}"

                await log(f"{self.log_prefix} failed: {media_item.url} with error: {e_log_detail}", 40)
                await self.manager.log_manager.write_download_error_log(media_item.url, e_log_message, e_origin)
                await self.manager.progress_manager.download_stats_progress.add_failure(e_ui_failure)
                await self.manager.progress_manager.download_progress.add_failed()
                await self.attempt_task_removal(media_item)
                return

            if isinstance(media_item.partial_file, Path) and media_item.partial_file.is_file():
                size = media_item.partial_file.stat().st_size
                if media_item.filename in self._current_attempt_filesize and self._current_attempt_filesize[
                    media_item.filename] >= size:
                    raise DownloadFailure(status=getattr(err, "status", type(err).__name__),
                                        message=f"{self.log_prefix} failed")
                self._current_attempt_filesize[media_item.filename] = size
                media_item.current_attempt = 0
                raise DownloadFailure(status=999, message="Download timeout reached, retrying")

            message = err.message if hasattr(err, "message") else str(err)
            raise DownloadFailure(status=getattr(err, "status", type(err).__name__), message=message)

    @staticmethod
    async def is_failed(status: int):
        return any((await is_4xx_client_error(status) and status != HTTPStatus.TOO_MANY_REQUESTS,
                    status in (
                    HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY, CustomHTTPStatus.WEB_SERVER_IS_DOWN)))
