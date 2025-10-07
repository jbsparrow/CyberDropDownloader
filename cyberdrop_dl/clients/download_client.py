from __future__ import annotations

import asyncio
import contextlib
import itertools
import time
from http import HTTPStatus
from typing import TYPE_CHECKING

import aiofiles

from cyberdrop_dl.constants import FILE_FORMATS
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DDOSGuardError, DownloadError, InvalidContentTypeError, SlowDownloadError
from cyberdrop_dl.utils.dates import parse_http_date
from cyberdrop_dl.utils.logger import log, log_debug
from cyberdrop_dl.utils.utilities import get_size_or_none

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Generator
    from pathlib import Path
    from typing import Any

    import aiohttp
    from multidict import CIMultiDictProxy

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.client_manager import ClientManager
    from cyberdrop_dl.managers.manager import Manager


_CONTENT_TYPES_OVERRIDES: dict[str, str] = {"text/vnd.trolltech.linguist": "video/MP2T"}
_SLOW_DOWNLOAD_PERIOD: int = 10  # seconds
_CHROME_ANDROID_USER_AGENT: str = (
    "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.180 Mobile Safari/537.36"
)
_FREE_SPACE_CHECK_PERIOD: int = 5  # Check every 5 chunks


class DownloadClient:
    """AIOHTTP operations for downloading."""

    def __init__(self, manager: Manager, client_manager: ClientManager) -> None:
        self.manager = manager
        self.client_manager = client_manager
        self.download_speed_threshold = self.manager.config_manager.settings_data.runtime_options.slow_download_speed

    @contextlib.asynccontextmanager
    async def _limiter(self, domain: str):
        with self.client_manager.request_context(domain):
            await self.client_manager.manager.states.RUNNING.wait()
            yield

    def _get_download_headers(self, domain: str, referer: AbsoluteHttpURL) -> dict[str, str]:
        download_headers = self.client_manager._default_headers | {"Referer": str(referer)}
        auth_data = self.manager.config_manager.authentication_data
        if domain == "pixeldrain" and auth_data.pixeldrain.api_key:
            download_headers["Authorization"] = self.manager.client_manager.basic_auth(
                "Cyberdrop-DL", auth_data.pixeldrain.api_key
            )
        elif domain == "gofile":
            gofile_cookies = self.client_manager.cookies.filter_cookies(AbsoluteHttpURL("https://gofile.io"))
            api_key = gofile_cookies.get("accountToken", "")
            if api_key:
                download_headers["Authorization"] = f"Bearer {api_key.value}"  # type: ignore
        elif domain == "odnoklassniki":
            # TODO: Add "headers" attribute to MediaItem to use custom headers for downloads
            download_headers |= {
                "Accept-Language": "en-gb, en;q=0.8",
                "User-Agent": _CHROME_ANDROID_USER_AGENT,
                "Referer": "https://m.ok.ru/",
                "Origin": "https://m.ok.ru",
            }
        elif domain == "megacloud":
            download_headers["Referer"] = "https://megacloud.blog/"
        return download_headers

    async def _download(self, domain: str, media_item: MediaItem) -> bool:
        """Downloads a file."""
        download_headers = self._get_download_headers(domain, media_item.referer)
        downloaded_filename = await self.manager.db_manager.history_table.get_downloaded_filename(domain, media_item)
        download_dir = self.get_download_dir(media_item)
        if media_item.is_segment:
            media_item.partial_file = media_item.complete_file = download_dir / media_item.filename
        else:
            media_item.partial_file = download_dir / f"{downloaded_filename}.part"

        resume_point = 0
        if media_item.partial_file and (size := await asyncio.to_thread(get_size_or_none, media_item.partial_file)):
            resume_point = size
            download_headers["Range"] = f"bytes={size}-"

        await asyncio.sleep(self.manager.config_manager.global_settings_data.rate_limiting_options.total_delay)

        async def process_response(resp: aiohttp.ClientResponse) -> bool:
            if resp.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                await asyncio.to_thread(media_item.partial_file.unlink)

            await self.client_manager.check_http_status(resp, download=True)

            if not media_item.is_segment:
                _ = get_content_type(media_item.ext, resp.headers)

            media_item.filesize = int(resp.headers.get("Content-Length", "0")) or None
            if not media_item.complete_file:
                proceed, skip = await self.get_final_file_info(media_item, domain)
                self.client_manager.check_content_length(resp.headers)
                if skip:
                    self.manager.progress_manager.download_progress.add_skipped()
                    return False
                if not proceed:
                    if media_item.is_segment:
                        return True
                    log(f"Skipping {media_item.url} as it has already been downloaded", 10)
                    self.manager.progress_manager.download_progress.add_previously_completed(False)
                    await self.process_completed(media_item, domain)
                    await self.handle_media_item_completion(media_item, downloaded=False)

                    return False

            if resp.status != HTTPStatus.PARTIAL_CONTENT:
                await asyncio.to_thread(media_item.partial_file.unlink, missing_ok=True)

            if not media_item.datetime and (last_modified := get_last_modified(resp.headers)):
                msg = f"Unable to parse upload date for {media_item.url}, using `Last-Modified` header as file datetime"
                log(msg, 30)
                media_item.datetime = last_modified

            task_id = media_item.task_id
            if task_id is None:
                size = (media_item.filesize + resume_point) if media_item.filesize is not None else None
                task_id = self.manager.progress_manager.file_progress.add_task(
                    domain=domain, filename=media_item.filename, expected_size=size
                )
                media_item.set_task_id(task_id)

            self.manager.progress_manager.file_progress.advance_file(task_id, resume_point)

            await self._append_content(media_item, resp.content)
            return True

        return await self._request_download(media_item, download_headers, process_response)

    async def _request_download(
        self,
        media_item: MediaItem,
        download_headers: dict[str, str],
        process_response: Callable[[aiohttp.ClientResponse], Coroutine[None, None, bool]],
    ) -> bool:
        download_url = media_item.debrid_link or media_item.url
        await self.manager.states.RUNNING.wait()
        fallback_url_generator = _fallback_generator(media_item)
        fallback_count = 0
        while True:
            resp = None
            try:
                async with self.client_manager._download_session.get(download_url, headers=download_headers) as resp:
                    return await process_response(resp)
            except (DownloadError, DDOSGuardError):
                if resp is None:
                    raise
                try:
                    next_download_url = fallback_url_generator.send(resp)
                except StopIteration:
                    pass
                else:
                    if not next_download_url:
                        raise
                    if media_item.debrid_link and media_item.debrid_link == download_url:
                        msg = f" with debrid URL {download_url} failed, retrying with fallback URL: "
                    elif media_item.url == download_url:
                        msg = " failed, retrying with fallback URL: "
                    else:
                        fallback_count += 1
                        msg = f" with fallback URL #{fallback_count} {download_url} failed, retrying with new fallback URL: "
                    log(f"Download of {media_item.url}{msg}{next_download_url}", 40)
                    download_url = next_download_url
                    continue
                raise

    async def _append_content(self, media_item: MediaItem, content: aiohttp.StreamReader) -> None:
        """Appends content to a file."""

        assert media_item.task_id is not None
        check_free_space = self.make_free_space_checker(media_item)
        check_download_speed = self.make_speed_checker(media_item)
        await check_free_space()
        await self._pre_download_check(media_item)

        async with aiofiles.open(media_item.partial_file, mode="ab") as f:
            async for chunk in content.iter_chunked(self.client_manager.speed_limiter.chunk_size):
                await self.manager.states.RUNNING.wait()
                await check_free_space()
                chunk_size = len(chunk)
                await self.client_manager.speed_limiter.acquire(chunk_size)
                await f.write(chunk)
                self.manager.progress_manager.file_progress.advance_file(media_item.task_id, chunk_size)
                check_download_speed()

        self._post_download_check(media_item, content)

    def _pre_download_check(self, media_item: MediaItem) -> Coroutine[Any, Any, None]:
        def prepare() -> None:
            media_item.partial_file.parent.mkdir(parents=True, exist_ok=True)
            if not media_item.partial_file.is_file():
                media_item.partial_file.touch()

        return asyncio.to_thread(prepare)

    def _post_download_check(self, media_item: MediaItem, content: aiohttp.StreamReader) -> None:
        if not content.total_bytes and not media_item.partial_file.stat().st_size:
            media_item.partial_file.unlink()
            raise DownloadError(status=HTTPStatus.INTERNAL_SERVER_ERROR, message="File is empty")

    def make_free_space_checker(self, media_item: MediaItem) -> Callable[[], Coroutine[Any, Any, None]]:
        current_chunk = 0

        async def check_free_space() -> None:
            nonlocal current_chunk
            if current_chunk % _FREE_SPACE_CHECK_PERIOD == 0:
                await self.manager.storage_manager.check_free_space(media_item)
            current_chunk += 1

        return check_free_space

    def make_speed_checker(self, media_item: MediaItem) -> Callable[[], None]:
        last_slow_speed_read = None

        def check_download_speed() -> None:
            nonlocal last_slow_speed_read
            if not self.download_speed_threshold:
                return
            assert media_item.task_id is not None
            speed = self.manager.progress_manager.file_progress.get_speed(media_item.task_id)
            if speed > self.download_speed_threshold:
                last_slow_speed_read = None
            elif not last_slow_speed_read:
                last_slow_speed_read = time.perf_counter()
            elif time.perf_counter() - last_slow_speed_read > _SLOW_DOWNLOAD_PERIOD:
                raise SlowDownloadError(origin=media_item)

        return check_download_speed

    async def download_file(self, domain: str, media_item: MediaItem) -> bool:
        """Starts a file."""
        if self.manager.config.download_options.skip_download_mark_completed and not media_item.is_segment:
            log(f"Download Removed {media_item.url} due to mark completed option", 10)
            self.manager.progress_manager.download_progress.add_skipped()
            # set completed path
            await self.process_completed(media_item, domain)
            return False

        async with self._limiter(domain):
            downloaded = await self._download(domain, media_item)

        if downloaded:
            await asyncio.to_thread(media_item.partial_file.rename, media_item.complete_file)
            if not media_item.is_segment:
                proceed = self.client_manager.check_file_duration(media_item)
                await self.manager.db_manager.history_table.add_duration(domain, media_item)
                if not proceed:
                    log(f"Download Skip {media_item.url} due to runtime restrictions", 10)
                    await asyncio.to_thread(media_item.complete_file.unlink)
                    await self.mark_incomplete(media_item, domain)
                    self.manager.progress_manager.download_progress.add_skipped()
                    return False
                await self.process_completed(media_item, domain)
                await self.handle_media_item_completion(media_item, downloaded=True)
        return downloaded

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def mark_incomplete(self, media_item: MediaItem, domain: str) -> None:
        """Marks the media item as incomplete in the database."""
        if media_item.is_segment:
            return
        await self.manager.db_manager.history_table.insert_incompleted(domain, media_item)

    async def process_completed(self, media_item: MediaItem, domain: str) -> None:
        """Marks the media item as completed in the database and adds to the completed list."""
        await self.mark_completed(domain, media_item)
        await self.add_file_size(domain, media_item)

    async def mark_completed(self, domain: str, media_item: MediaItem) -> None:
        await self.manager.db_manager.history_table.mark_complete(domain, media_item)

    async def add_file_size(self, domain: str, media_item: MediaItem) -> None:
        if not media_item.complete_file:
            media_item.complete_file = self.get_file_location(media_item)
        if await asyncio.to_thread(media_item.complete_file.is_file):
            await self.manager.db_manager.history_table.add_filesize(domain, media_item)

    async def handle_media_item_completion(self, media_item: MediaItem, downloaded: bool = False) -> None:
        """Sends to hash client to handle hashing and marks as completed/current download."""
        try:
            media_item.downloaded = downloaded
            await self.manager.hash_manager.hash_client.hash_item_during_download(media_item)
            self.manager.path_manager.add_completed(media_item)
        except Exception:
            log(f"Error handling media item completion of: {media_item.complete_file}", 10, exc_info=True)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def get_download_dir(self, media_item: MediaItem) -> Path:
        """Returns the download directory for the media item."""
        download_folder = media_item.download_folder
        if self.manager.parsed_args.cli_only_args.retry_any:
            return download_folder

        if self.manager.config_manager.settings_data.download_options.block_download_sub_folders:
            while download_folder.parent != self.manager.path_manager.download_folder:
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

        expected_size = media_item.filesize
        proceed = True
        skip = False

        if not TYPE_CHECKING:
            log = log_debug if media_item.is_segment else globals()["log"]

        while True:
            if expected_size and not media_item.is_segment:
                file_size_check = self.check_filesize_limits(media_item)
                if not file_size_check:
                    log(f"Download Skip {media_item.url} due to filesize restrictions", 10)
                    proceed = False
                    skip = True
                    return proceed, skip

            if not media_item.complete_file.exists() and not media_item.partial_file.exists():
                break

            if media_item.complete_file.exists() and media_item.complete_file.stat().st_size == media_item.filesize:
                log(f"Found {media_item.complete_file.name} locally, skipping download")
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
                    log(f"Found {downloaded_filename} locally, trying to resume")
                    assert media_item.filesize
                    size = media_item.partial_file.stat().st_size
                    if size >= media_item.filesize != 0:
                        log(f"Deleting partial file {media_item.partial_file}")
                        media_item.partial_file.unlink()

                    elif size == media_item.filesize:
                        if media_item.complete_file.exists():
                            log(
                                f"Found conflicting complete file '{media_item.complete_file}' locally, iterating filename",
                                30,
                            )
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
                        log(
                            f"Renaming found partial file '{media_item.partial_file}' to complete file {media_item.complete_file}"
                        )
                elif media_item.complete_file.exists():
                    if media_item.complete_file.stat().st_size == media_item.filesize:
                        log(f"Found complete file '{media_item.complete_file}' locally, skipping download")
                        proceed = False
                    else:
                        log(
                            f"Found conflicting complete file '{media_item.complete_file}' locally, iterating filename",
                            30,
                        )
                        media_item.complete_file, media_item.partial_file = await self.iterate_filename(
                            media_item.complete_file,
                            media_item,
                        )
                break

            media_item.filename = downloaded_filename
        media_item.download_filename = media_item.complete_file.name
        await self.manager.db_manager.history_table.add_download_filename(domain, media_item)
        return proceed, skip

    async def iterate_filename(self, complete_file: Path, media_item: MediaItem) -> tuple[Path, Path]:
        """Iterates the filename until it is unique."""
        partial_file = complete_file.with_suffix(complete_file.suffix + ".part")
        for iteration in itertools.count(1):
            filename = f"{complete_file.stem} ({iteration}){complete_file.suffix}"
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
        file_size_limits = self.manager.config_manager.settings_data.file_size_limits
        max_video_filesize = file_size_limits.maximum_video_size or float("inf")
        min_video_filesize = file_size_limits.minimum_video_size
        max_image_filesize = file_size_limits.maximum_image_size or float("inf")
        min_image_filesize = file_size_limits.minimum_image_size
        max_other_filesize = file_size_limits.maximum_other_size or float("inf")
        min_other_filesize = file_size_limits.minimum_other_size

        assert media.filesize is not None
        if media.ext in FILE_FORMATS["Images"]:
            proceed = min_image_filesize < media.filesize < max_image_filesize
        elif media.ext in FILE_FORMATS["Videos"]:
            proceed = min_video_filesize < media.filesize < max_video_filesize
        else:
            proceed = min_other_filesize < media.filesize < max_other_filesize

        return proceed


def get_content_type(ext: str, headers: CIMultiDictProxy) -> str | None:
    content_type: str = headers.get("Content-Type", "")
    content_length = headers.get("Content-Length")
    if not content_type and not content_length:
        msg = "No content type in response headers"
        raise InvalidContentTypeError(message=msg)

    if not content_type:
        return None

    override_key = next((name for name in _CONTENT_TYPES_OVERRIDES if name in content_type), "<NO_OVERRIDE>")
    override: str | None = _CONTENT_TYPES_OVERRIDES.get(override_key)
    content_type = override or content_type
    content_type = content_type.lower()

    if is_html_or_text(content_type) and ext.lower() not in FILE_FORMATS["Text"]:
        msg = f"Received '{content_type}', was expecting other"
        raise InvalidContentTypeError(message=msg)

    return content_type


def get_last_modified(headers: CIMultiDictProxy) -> int | None:
    if date_str := headers.get("Last-Modified"):
        return parse_http_date(date_str)


def is_html_or_text(content_type: str) -> bool:
    return any(s in content_type for s in ("html", "text"))


def _fallback_generator(media_item: MediaItem):
    fallbacks = media_item.fallbacks

    def gen_fallback() -> Generator[AbsoluteHttpURL | None, aiohttp.ClientResponse, None]:
        response = yield
        if fallbacks is None:
            return

        if callable(fallbacks):
            for retry in itertools.count(1):
                if not response:
                    return
                url = fallbacks(response, retry)
                if not url:
                    return
                response = yield url

        else:
            yield from fallbacks

    gen = gen_fallback()
    next(gen)  # Prime the generator, waiting for response
    return gen
