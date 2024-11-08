from __future__ import annotations

import asyncio
import copy
import itertools
from functools import partial, wraps
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import aiohttp
from aiohttp import ClientSession

from cyberdrop_dl.clients.errors import DownloadError, InsufficientFreeSpaceError, InvalidContentTypeError
from cyberdrop_dl.utils.constants import DEBUG_VAR, FILE_FORMATS
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from cyberdrop_dl.managers.client_manager import ClientManager
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem


def is_4xx_client_error(status_code: int) -> bool:
    """Checks whether the HTTP status code is 4xx client error."""
    if isinstance(status_code, str):
        return True
    return HTTPStatus.BAD_REQUEST <= status_code < HTTPStatus.INTERNAL_SERVER_ERROR


def limiter(func: Callable) -> Any:
    """Wrapper handles limits for download session."""

    @wraps(func)
    async def wrapper(self: DownloadClient, *args, **kwargs) -> Any:
        domain_limiter = await self.client_manager.get_rate_limiter(args[0])
        await asyncio.sleep(await self.client_manager.get_downloader_spacer(args[0]))
        await self._global_limiter.acquire()
        await domain_limiter.acquire()

        async with aiohttp.ClientSession(
            headers=self._headers,
            raise_for_status=False,
            cookie_jar=self.client_manager.cookies,
            timeout=self._timeouts,
            trace_configs=self.trace_configs,
        ) as client:
            kwargs["client_session"] = client
            return await func(self, *args, **kwargs)

    return wrapper


class DownloadClient:
    """AIOHTTP operations for downloading."""

    def __init__(self, manager: Manager, client_manager: ClientManager) -> None:
        self.manager = manager
        self.client_manager = client_manager

        self._headers = {"user-agent": client_manager.user_agent}
        self._timeouts = aiohttp.ClientTimeout(
            total=client_manager.read_timeout + client_manager.connection_timeout,
            connect=client_manager.connection_timeout,
        )
        self._global_limiter = self.client_manager.global_rate_limiter
        self.trace_configs = []
        self._file_path = None
        if DEBUG_VAR:
            self.add_request_log_hooks()

    def add_request_log_hooks(self) -> None:
        async def on_request_start(*args):
            params: aiohttp.TraceRequestStartParams = args[2]
            log(f"Starting download {params.method} request to {params.url}", 40)

        async def on_request_end(*args):
            params: aiohttp.TraceRequestEndParams = args[2]
            log(f"Finishing download {params.method} request to {params.url}", 40)
            log(f"Response status for {params.url}: {params.response.status}", 40)

        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(on_request_start)
        trace_config.on_request_end.append(on_request_end)
        self.trace_configs.append(trace_config)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @limiter
    async def _download(
        self,
        domain: str,
        manager: Manager,
        media_item: MediaItem,
        save_content: Callable[[aiohttp.StreamReader], Coroutine[Any, Any, None]],
        client_session: ClientSession,
    ) -> bool:
        """Downloads a file."""
        download_headers = copy.deepcopy(self._headers)
        download_headers["Referer"] = str(media_item.referer)
        if (
            domain == "pixeldrain"
            and self.manager.config_manager.authentication_data["PixelDrain"]["pixeldrain_api_key"]
        ):
            download_headers["Authorization"] = self.manager.download_manager.basic_auth(
                "Cyberdrop-DL",
                self.manager.config_manager.authentication_data["PixelDrain"]["pixeldrain_api_key"],
            )

        downloaded_filename = await self.manager.db_manager.history_table.get_downloaded_filename(domain, media_item)
        download_dir = self.get_download_dir(media_item)
        media_item.partial_file = download_dir / f"{downloaded_filename}.part"

        resume_point = 0
        if isinstance(media_item.partial_file, Path) and media_item.partial_file.exists():
            resume_point = media_item.partial_file.stat().st_size if media_item.partial_file.exists() else 0
            download_headers["Range"] = f"bytes={resume_point}-"

        await asyncio.sleep(self.client_manager.download_delay)

        download_url = media_item.debrid_link or media_item.url
        async with client_session.get(
            download_url,
            headers=download_headers,
            ssl=self.client_manager.ssl_context,
            proxy=self.client_manager.proxy,
        ) as resp:
            if resp.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                media_item.partial_file.unlink()

            await self.client_manager.check_http_status(resp, download=True, origin=media_item.url)
            content_type = resp.headers.get("Content-Type")

            media_item.filesize = int(resp.headers.get("Content-Length", "0"))
            if not isinstance(media_item.complete_file, Path):
                proceed, skip = await self.get_final_file_info(media_item, domain)
                await self.mark_incomplete(media_item, domain)
                self.client_manager.check_bunkr_maint(resp.headers)
                if skip:
                    self.manager.progress_manager.download_progress.add_skipped()
                    return False
                if not proceed:
                    log(f"Skipping {media_item.url} as it has already been downloaded", 10)
                    self.manager.progress_manager.download_progress.add_previously_completed(False)
                    await self.process_completed(media_item, domain)
                    await self.handle_media_item_completion(media_item, downloaded=False)

                    return False

            ext = Path(media_item.filename).suffix.lower()
            if (
                content_type
                and any(s in content_type.lower() for s in ("html", "text"))
                and ext not in FILE_FORMATS["Text"]
            ):
                raise InvalidContentTypeError(message=f"Received {content_type}, was expecting other")

            if resp.status != HTTPStatus.PARTIAL_CONTENT and media_item.partial_file.is_file():
                media_item.partial_file.unlink()

            media_item.task_id = self.manager.progress_manager.file_progress.add_task(
                f"({domain.upper()}) {media_item.filename}",
                media_item.filesize + resume_point,
            )
            if media_item.partial_file.is_file():
                resume_point = media_item.partial_file.stat().st_size
                self.manager.progress_manager.file_progress.advance_file(media_item.task_id, resume_point)

            await save_content(resp.content)
            return True

    async def _append_content(
        self,
        media_item: MediaItem,
        content: aiohttp.StreamReader,
        update_progress: partial,
    ) -> None:
        """Appends content to a file."""
        if not self.client_manager.manager.download_manager.check_free_space(media_item.download_folder):
            raise InsufficientFreeSpaceError(origin=media_item)

        media_item.partial_file.parent.mkdir(parents=True, exist_ok=True)
        if not media_item.partial_file.is_file():
            media_item.partial_file.touch()
        async with aiofiles.open(media_item.partial_file, mode="ab") as f:  # type: ignore
            async for chunk, _ in content.iter_chunks():
                await self.client_manager.check_bucket(chunk)
                await asyncio.sleep(0)
                await f.write(chunk)
                update_progress(len(chunk))
        if not content.total_bytes and not media_item.partial_file.stat().st_size:
            media_item.partial_file.unlink()
            raise DownloadError(status=HTTPStatus.INTERNAL_SERVER_ERROR, message="File is empty")

    async def download_file(self, manager: Manager, domain: str, media_item: MediaItem) -> bool:
        """Starts a file."""
        if self.manager.config_manager.settings_data["Download_Options"]["skip_download_mark_completed"]:
            log(f"Download Skip {media_item.url} due to mark completed option", 10)
            self.manager.progress_manager.download_progress.add_skipped()
            # set completed path
            await self.mark_incomplete(media_item, domain)
            await self.process_completed(media_item, domain)
            return False

        async def save_content(content: aiohttp.StreamReader) -> None:
            await self._append_content(
                media_item,
                content,
                partial(manager.progress_manager.file_progress.advance_file, media_item.task_id),
            )

        downloaded = await self._download(domain, manager, media_item, save_content)
        if downloaded:
            media_item.partial_file.rename(media_item.complete_file)
            await self.process_completed(media_item, domain)
            await self.handle_media_item_completion(media_item, downloaded=True)
        return downloaded

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def mark_incomplete(self, media_item: MediaItem, domain: str) -> None:
        """Marks the media item as incomplete in the database."""
        await self.manager.db_manager.history_table.insert_incompleted(domain, media_item)

    async def process_completed(self, media_item: MediaItem, domain: str) -> None:
        """Marks the media item as completed in the database and adds to the completed list."""
        await self.mark_completed(domain, media_item)
        await self.add_file_size(domain, media_item)

    async def mark_completed(self, domain: str, media_item: MediaItem) -> None:
        await self.manager.db_manager.history_table.mark_complete(domain, media_item)

    async def add_file_size(self, domain: str, media_item: MediaItem) -> None:
        if not isinstance(media_item.complete_file, Path):
            media_item.complete_file = self.get_file_location(media_item)
        if media_item.complete_file.exists():
            await self.manager.db_manager.history_table.add_filesize(domain, media_item)

    async def handle_media_item_completion(self, media_item: MediaItem, downloaded: bool = False) -> None:
        """Sends to hash client to handle hashing and marks as completed/current download."""
        try:
            await self.manager.hash_manager.hash_client.hash_item_during_download(media_item)
            if (
                downloaded
                or self.manager.config_manager.global_settings_data["Dupe_Cleanup_Options"]["dedupe_already_downloaded"]
            ):
                self.manager.path_manager.add_completed(media_item)
            if not downloaded:
                self.manager.path_manager.add_prev(media_item)
        except Exception:
            log(f"Error handling media item completion of: {media_item.complete_file}", 10, exc_info=True)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def get_download_dir(self, media_item: MediaItem) -> Path:
        """Returns the download directory for the media item."""
        download_folder = media_item.download_folder
        if self.manager.args_manager.retry_any:
            return download_folder

        if self.manager.config_manager.settings_data["Download_Options"]["block_download_sub_folders"]:
            while download_folder.parent != self.manager.path_manager.download_dir:
                download_folder = download_folder.parent
            media_item.download_folder = download_folder
        return download_folder

    def get_file_location(self, media_item: MediaItem) -> Path:
        download_dir = self.get_download_dir(media_item)
        return download_dir / media_item.filename

    async def get_final_file_info(self, media_item: MediaItem, domain: str) -> tuple[bool, bool]:
        """Complicated checker for if a file already exists, and was already downloaded."""
        media_item.complete_file = self.get_file_location(media_item)
        media_item.partial_file = media_item.complete_file.with_suffix(media_item.complete_file.suffix + ".part")

        expected_size = media_item.filesize if isinstance(media_item.filesize, int) else None
        proceed = True
        skip = False

        if not skip and self.manager.config_manager.settings_data["Ignore_Options"]["skip_hosts"]:
            skip_hosts = self.manager.config_manager.settings_data["Ignore_Options"]["skip_hosts"]
            if any(host in media_item.url.host for host in skip_hosts):
                log(f"Download Skip {media_item.url} due to skip_hosts config", 10)
                skip = True

        if not skip and self.manager.config_manager.settings_data["Ignore_Options"]["only_hosts"]:
            only_hosts = self.manager.config_manager.settings_data["Ignore_Options"]["only_hosts"]
            if not any(host in media_item.url.host for host in only_hosts):
                log(f"Download Skip {media_item.url} due to only_hosts config", 10)
                skip = True

        if skip:
            return proceed, skip

        while True:
            if expected_size:
                file_size_check = self.check_filesize_limits(media_item)
                if not file_size_check:
                    log(f"Download Skip {media_item.url} due to filesize restrictions", 10)
                    proceed = False
                    skip = True
                    return proceed, skip

            if not media_item.complete_file.exists() and not media_item.partial_file.exists():
                break

            if media_item.complete_file.exists() and media_item.complete_file.stat().st_size == media_item.filesize:
                proceed = False
                break

            downloaded_filename = await self.manager.db_manager.history_table.get_downloaded_filename(
                domain,
                media_item,
            )
            if not downloaded_filename:
                media_item.complete_file, media_item.partial_file = await self.iterate_filename(
                    media_item.complete_file,
                    media_item,
                )
                break

            if media_item.filename == downloaded_filename:
                if media_item.partial_file.exists():
                    if media_item.partial_file.stat().st_size >= media_item.filesize != 0:
                        media_item.partial_file.unlink()
                    if media_item.partial_file.stat().st_size == media_item.filesize:
                        if media_item.complete_file.exists():
                            new_complete_filename, new_partial_file = await self.iterate_filename(
                                media_item.complete_file,
                                media_item,
                            )
                            media_item.partial_file.rename(new_complete_filename)
                            proceed = False

                            media_item.complete_file = new_complete_filename
                            media_item.partial_file = new_partial_file
                        else:
                            proceed = False
                            media_item.partial_file.rename(media_item.complete_file)
                elif media_item.complete_file.exists():
                    if media_item.complete_file.stat().st_size == media_item.filesize:
                        proceed = False
                    else:
                        media_item.complete_file, media_item.partial_file = await self.iterate_filename(
                            media_item.complete_file,
                            media_item,
                        )
                break

            media_item.filename = downloaded_filename
        media_item.download_filename = media_item.complete_file.name
        return proceed, skip

    async def iterate_filename(self, complete_file: Path, media_item: MediaItem) -> tuple[Path, Path | None]:
        """Iterates the filename until it is unique."""
        partial_file = None
        for iteration in itertools.count(1):
            filename = f"{complete_file.stem} ({iteration}){media_item.ext}"
            temp_complete_file = media_item.download_folder / filename
            if (
                not temp_complete_file.exists()
                and not await self.manager.db_manager.history_table.check_filename_exists(filename)
            ):
                media_item.filename = filename
                complete_file = media_item.download_folder / media_item.filename
                partial_file = complete_file.with_suffix(complete_file.suffix + ".part")
                break
        return complete_file, partial_file

    def check_filesize_limits(self, media: MediaItem) -> bool:
        """Checks if the file size is within the limits."""
        file_size_limits = self.manager.config_manager.settings_data["File_Size_Limits"]
        max_video_filesize = file_size_limits["maximum_video_size"] or float("inf")
        min_video_filesize = file_size_limits["minimum_video_size"]
        max_image_filesize = file_size_limits["maximum_image_size"] or float("inf")
        min_image_filesize = file_size_limits["minimum_image_size"]
        max_other_filesize = file_size_limits["maximum_other_size"] or float("inf")
        min_other_filesize = file_size_limits["minimum_other_size"]

        if media.ext in FILE_FORMATS["Images"]:
            proceed = min_image_filesize < media.filesize < max_image_filesize
        elif media.ext in FILE_FORMATS["Videos"]:
            proceed = min_video_filesize < media.filesize < max_video_filesize
        else:
            proceed = min_other_filesize < media.filesize < max_other_filesize

        return proceed

    @property
    def file_path(self) -> str | None:
        return self._file_path

    @file_path.setter
    def file_path(self, media_item: MediaItem):
        self._file_path = media_item.filename
