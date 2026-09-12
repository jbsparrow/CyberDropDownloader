from __future__ import annotations

import asyncio
import itertools
import logging
import time
from contextvars import ContextVar
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, ClassVar, final

from aiohttp import hdrs

from cyberdrop_dl import aio, constants, ffmpeg, storage
from cyberdrop_dl.clients import etag
from cyberdrop_dl.clients.http import JSON_CHECK, check_http_status
from cyberdrop_dl.constants import USE_RETRY_PATH, FileExt
from cyberdrop_dl.exceptions import DownloadError, InvalidContentTypeError, SlowDownloadError
from cyberdrop_dl.signature import simple_repr
from cyberdrop_dl.utils import dates, enter_context

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path
    from typing import Any

    from cyberdrop_dl.clients.http import HTTPClient
    from cyberdrop_dl.clients.response import AbstractResponse
    from cyberdrop_dl.config import Config
    from cyberdrop_dl.manager import Manager
    from cyberdrop_dl.progress import ProgressHook
    from cyberdrop_dl.url_objects import MediaItem


logger = logging.getLogger(__name__)

IGNORE_CONTENT_TYPE: ContextVar[bool] = ContextVar("IGNORE_CONTENT_TYPE", default=False)
_CONTENT_TYPES_OVERRIDES: dict[str, str] = {"text/vnd.trolltech.linguist": "video/MP2T"}
_SLOW_DOWNLOAD_PERIOD: int = 10  # seconds


@final
class DownloadClient:
    """Low level class that performs the actual HTTP download operations."""

    SUPPORTS_RANGES: ClassVar[bool] = True

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.config = self.manager.config
        self.download_speed_threshold = self.config.downloads.slow_speed
        speed_limit = self.config.downloads.speed_limit

        self.speed_limiter = aio.RateLimiter(speed_limit, time_period=1)
        self.chunk_size: int = 1024 * 1024 * 10  # 10MB
        if speed_limit:
            upper_limit = int(speed_limit / 1.5 / self.config.downloads.concurrency)
            self.chunk_size = min(
                self.chunk_size,
                upper_limit,
            )

    __repr__ = simple_repr("config", "_supports_ranges", "speed_limiter", "chunk_size")

    @property
    def http_client(self) -> HTTPClient:
        return self.manager.http_client

    async def _download(self, domain: str, media_item: MediaItem) -> bool:
        """Downloads a file."""
        if media_item.is_segment:
            media_item.partial_file = media_item.path = media_item.download_folder / media_item.filename
        else:
            name = (
                await self.manager.database.history.get_downloaded_filename(domain, media_item) or media_item.filename
            )
            media_item.download_folder = resolve_download_dir(media_item.download_folder, self.config)
            media_item.partial_file = media_item.download_folder / f"{name}{constants.TempExt.PART}"

        resume_point = 0
        media_item.headers.pop(hdrs.RANGE, None)  # Delete ranges from previous attempts
        if self.SUPPORTS_RANGES and media_item.partial_file and (size := await aio.get_size(media_item.partial_file)):
            resume_point = size
            media_item.headers[hdrs.RANGE] = f"bytes={size}-"

        await asyncio.sleep(self.config.downloads.total_delay)

        download_url = await media_item.resolve()
        with enter_context(JSON_CHECK, media_item.json_check):
            async with self.http_client.raw_request(
                download_url,
                headers=media_item.headers,
                impersonate=media_item.extra_info.get("impersonate"),
            ) as resp:
                return await self._process_response(media_item, domain, resume_point, resp)

    async def _predownload_skip(self, media_item: MediaItem, domain: str) -> bool | None:
        should_download, should_skip = await self.get_final_file_info(media_item, domain)
        if should_skip:
            self.manager.scrape_mapper.tui.files.stats.skipped += 1
            return False
        if not should_download:
            if media_item.is_segment:
                return True
            logger.info(f"Skipping {media_item.url} as it has already been downloaded")
            self.manager.scrape_mapper.tui.files.stats.prev_completed += 1
            await self.mark_completed(media_item, domain)
            return False
        return None

    async def _process_response(
        self,
        media_item: MediaItem,
        domain: str,
        resume_point: int,
        resp: AbstractResponse[Any],
    ) -> bool:
        await _check_response(media_item, resp, resume_point)
        media_item.size = _get_content_length(resp.headers)
        if resp.status == HTTPStatus.PARTIAL_CONTENT:
            # Content-Length of a ranged response only counts the bytes after resume_point.
            # Every check below (partial size, final size, filesize limits) needs the size of the whole file
            media_item.size += resume_point
        _set_upload_date(media_item, resp.headers)
        if not media_item.path:
            downloaded = await self._predownload_skip(media_item, domain)
            if downloaded is not None:
                return downloaded

        hook = self._make_hook(media_item)
        if resume_point:
            hook.advance(resume_point)

        with hook:
            await self._append_content(media_item, hook, resp)
            return True

    def _make_hook(self, media_item: MediaItem) -> ProgressHook:
        if media_item.is_segment and not media_item.extra_info.get("MUX_STREAM"):
            return self.manager.scrape_mapper.tui.downloads.download_hls_seg()

        size = media_item.size
        return self.manager.scrape_mapper.tui.downloads.download_file(
            media_item.filename,
            media_item.domain,
            size,
            url=media_item.url,
        )

    def _track_speed(self, hook: ProgressHook):
        "force update task speed at least every 0.1 seconds"

        async def update_speed() -> None:
            hook.advance(0)

        return aio.backgroud_task(update_speed, period=0.1)

    async def _append_content(self, media_item: MediaItem, hook: ProgressHook, resp: AbstractResponse[Any]) -> None:
        check_free_space = storage.create_free_space_checker(media_item)
        check_download_speed = make_speed_checker(media_item, hook, self.download_speed_threshold)
        await check_free_space(_get_content_length(resp.headers))
        await self._pre_download_check(media_item)

        async with self._track_speed(hook), aio.open(media_item.partial_file, mode="ab") as f:
            async for chunk in resp.iter_chunked(self.chunk_size):
                n_bytes = len(chunk)
                await self.speed_limiter.acquire(n_bytes)
                await check_free_space()
                await f.write(chunk)
                hook.advance(n_bytes)
                check_download_speed()

        await self._post_download_check(media_item)

    @aio.to_thread
    def _pre_download_check(self, media_item: MediaItem) -> None:
        media_item.partial_file.parent.mkdir(parents=True, exist_ok=True)
        if not media_item.partial_file.is_file():
            media_item.partial_file.touch()

    async def _post_download_check(self, media_item: MediaItem, *_: Any) -> None:
        size = await aio.get_size(media_item.partial_file)
        if not size:
            await aio.unlink(media_item.partial_file, missing_ok=True)
            raise DownloadError(HTTPStatus.INTERNAL_SERVER_ERROR, "File is empty")

        assert media_item.size is not None
        if size < media_item.size:
            await aio.unlink(media_item.partial_file, missing_ok=True)
            msg = f"Expected at least {media_item.size:,} bytes but only got {size:,} bytes"
            raise DownloadError("Corrupted File", msg)

    async def download_file(self, domain: str, media_item: MediaItem) -> bool:
        """Starts a file."""
        if self.config.downloads.skip_and_mark_completed and not media_item.is_segment:
            logger.info(f"Download skipped {media_item.url} due to `--skip-and-mark-completed` option")
            self.manager.scrape_mapper.tui.files.stats.skipped += 1
            # set completed path
            await self.mark_completed(media_item, domain)
            return False

        downloaded = await self._download(domain, media_item)
        if downloaded:
            await aio.move(media_item.partial_file, media_item.path)
        return downloaded

    async def mark_incomplete(self, media_item: MediaItem, domain: str) -> None:
        if media_item.is_segment:
            return
        await self.manager.database.history.insert_incompleted(domain, media_item)

    async def mark_completed(self, media_item: MediaItem, domain: str) -> None:
        await self.manager.database.history.mark_complete(domain, media_item)
        if not media_item.path:
            media_item.path = media_item.download_folder / media_item.filename

        if await aio.is_file(media_item.path):
            await self.manager.database.history.add_filesize(domain, media_item)

    async def get_final_file_info(self, media_item: MediaItem, domain: str) -> tuple[bool, bool]:  # noqa: C901, PLR0912, PLR0915
        """Complicated checker for if a file already exists, and was already downloaded."""
        if not media_item.path:
            media_item.path = media_item.download_folder / media_item.filename

        part_suffix = media_item.path.suffix + constants.TempExt.PART
        media_item.partial_file = media_item.path.with_suffix(part_suffix)

        expected_size = media_item.size
        proceed = True
        skip = False

        while True:
            if expected_size and not media_item.is_segment:
                file_size_check = _check_filesize_limits(media_item, self.config)
                if not file_size_check:
                    logger.info("Download skipped %s due to filesize restrictions", media_item.url)
                    proceed = False
                    skip = True
                    return proceed, skip

            if not media_item.path.exists() and not media_item.partial_file.exists():
                break

            if media_item.path.exists() and media_item.path.stat().st_size == media_item.size:
                logger.info(f"Found {media_item.path.name} locally, skipping download")
                proceed = False
                break

            downloaded_filename = await self.manager.database.history.get_downloaded_filename(
                domain,
                media_item,
            )
            if not downloaded_filename:
                media_item.path, media_item.partial_file = await self.iterate_filename(
                    media_item.path,
                    media_item,
                )
                break

            if media_item.filename == downloaded_filename:
                if media_item.partial_file.exists():
                    logger.info(f"Found {downloaded_filename} locally, trying to resume")
                    assert media_item.size
                    size = media_item.partial_file.stat().st_size
                    if size >= media_item.size:
                        logger.info(f"Deleting partial file {media_item.partial_file}. Size is out of bound")
                        media_item.partial_file.unlink()

                    elif size == media_item.size:
                        if media_item.path.exists():
                            logger.warning(
                                f"Found conflicting complete file '{media_item.path}' locally, iterating filename"
                            )
                            new_complete_filename, new_partial_file = await self.iterate_filename(
                                media_item.path,
                                media_item,
                            )
                            media_item.partial_file.rename(new_complete_filename)
                            proceed = False

                            media_item.path = new_complete_filename
                            media_item.partial_file = new_partial_file
                        else:
                            proceed = False
                            media_item.partial_file.rename(media_item.path)
                        logger.info(
                            f"Renaming found partial file '{media_item.partial_file}' to complete file {media_item.path}"
                        )
                elif media_item.path.exists():
                    if media_item.path.stat().st_size == media_item.size:
                        logger.info(f"Found complete file '{media_item.path}' locally, skipping download")
                        proceed = False
                    else:
                        logger.warning(
                            f"Found conflicting complete file '{media_item.path}' locally, iterating filename"
                        )
                        media_item.path, media_item.partial_file = await self.iterate_filename(
                            media_item.path,
                            media_item,
                        )
                break

            media_item.filename = downloaded_filename
        media_item.download_filename = media_item.path.name
        await self.manager.database.history.add_download_filename(domain, media_item)
        return proceed, skip

    async def iterate_filename(self, complete_file: Path, media_item: MediaItem) -> tuple[Path, Path]:
        """Iterates the filename until it is unique."""
        part_suffix = complete_file.suffix + constants.TempExt.PART
        partial_file = complete_file.with_suffix(part_suffix)
        for iteration in itertools.count(1):
            filename = f"{complete_file.stem} ({iteration}){complete_file.suffix}"
            temp_complete_file = media_item.download_folder / filename
            if not temp_complete_file.exists() and not await self.manager.database.history.check_filename_exists(
                filename
            ):
                media_item.filename = filename
                complete_file = media_item.download_folder / media_item.filename
                partial_file = complete_file.with_suffix(part_suffix)
                break
        return complete_file, partial_file


def _check_filesize_limits(media: MediaItem, config: Config) -> bool:
    limits = config.filters.sizes.ranges

    assert media.size is not None
    if media.ext in FileExt.IMAGE:
        return not limits.image or media.size in limits.image
    if media.ext in FileExt.VIDEO:
        return not limits.video or media.size in limits.video
    if media.ext in FileExt.AUDIO:
        return not limits.image or media.size in limits.image

    return not limits.non_media or media.size in limits.non_media


def _check_content_type(content_type: str, ext: str) -> str | None:
    if IGNORE_CONTENT_TYPE.get():
        return
    if _is_html_or_text(content_type) and ext.lower() not in FileExt.TEXT:
        msg = f"Received '{content_type}', was expecting binary payload"
        raise InvalidContentTypeError(message=msg)


def _get_content_type(headers: Mapping[str, str]) -> str | None:
    content_type = headers.get(hdrs.CONTENT_TYPE)
    if not content_type:
        return None

    override_key = next((name for name in _CONTENT_TYPES_OVERRIDES if name in content_type), "<NO_OVERRIDE>")
    return _CONTENT_TYPES_OVERRIDES.get(override_key) or content_type


def _get_last_modified(headers: Mapping[str, str]) -> int | None:
    if date_str := headers.get(hdrs.LAST_MODIFIED):
        return int(dates.parse_http(date_str).timestamp())


def _is_html_or_text(content_type: str) -> bool:
    return "html" in content_type or "text" in content_type


def _check_for_placeholder_files(headers: Mapping[str, str]) -> None:
    match headers.get(hdrs.CONTENT_TYPE):
        case "video/mp4":
            match headers.get(hdrs.CONTENT_LENGTH):
                case "322509":
                    raise DownloadError("Bunkr Maintenance", "Bunkr under maintenance")
                case "73003":
                    raise DownloadError(410)  # Placeholder video with text "Video removed" (efukt)
                case _:
                    return
        case _:
            return


async def filter_by_duration(media_item: MediaItem, config: Config) -> bool:
    if media_item.is_segment:
        return False

    duration_limits = config.filters.duration.ranges
    if media_item.ext.lower() in FileExt.VIDEO:
        limits = duration_limits.video
    elif media_item.ext.lower() in FileExt.AUDIO:
        limits = duration_limits.audio
    else:
        return False

    if limits is None:
        return False

    if media_item.duration is None:
        media_item.duration = _get_duration(await _probe_item(media_item, config))
    if media_item.duration is None:
        return False

    return media_item.duration not in limits


async def _probe_item(media_item: MediaItem, config: Config) -> ffmpeg.FFprobeResult:
    if media_item.downloaded:
        return await ffmpeg.probe(media_item.path)

    return await ffmpeg.probe_url(
        media_item.url,
        headers=media_item.headers,
        proxy=config.network.proxy,
        verify=config.network.tls.verify,
    )


def _get_duration(properties: ffmpeg.FFprobeResult) -> float | None:
    if properties.format.duration:
        return properties.format.duration
    if properties.video:
        return properties.video.duration
    if properties.audio:
        return properties.audio.duration


def make_speed_checker(media_item: MediaItem, hook: ProgressHook, speed_threshold: int) -> Callable[[], None]:
    last_slow_speed_read = None

    def check_download_speed() -> None:
        nonlocal last_slow_speed_read
        if not speed_threshold:
            return

        speed = hook.get_speed()
        if speed > speed_threshold:
            last_slow_speed_read = None
        elif not last_slow_speed_read:
            last_slow_speed_read = time.perf_counter()
        elif time.perf_counter() - last_slow_speed_read > _SLOW_DOWNLOAD_PERIOD:
            raise SlowDownloadError(origin=media_item)

    return check_download_speed


def _get_content_length(headers: Mapping[str, str], *, _required: bool = False) -> int:
    try:
        return int(headers[hdrs.CONTENT_LENGTH])
    except KeyError:
        if not _required:
            return 0
        msg = f"Download response has no `{hdrs.CONTENT_LENGTH}` header. Refusing to download"
        raise DownloadError(HTTPStatus.LENGTH_REQUIRED, msg, retry=False) from None


def _set_upload_date(media_item: MediaItem, headers: Mapping[str, str]) -> None:
    if not media_item.is_segment and not media_item.uploaded_at and (last_modified := _get_last_modified(headers)):
        logger.warning(
            "Unable to parse upload date for %s, using `%s` header as file datetime",
            media_item.url,
            hdrs.LAST_MODIFIED,
        )
        media_item.uploaded_at = last_modified


async def _check_response(media_item: MediaItem, resp: AbstractResponse[Any], resume_point: int) -> None:
    if resp.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
        logger.warning(
            "Deleting partial file '%s'. Download is corrupted. Partial file is bigger that expected size",
            media_item.partial_file,
        )
        await aio.unlink(media_item.partial_file)

    etag.check(resp.headers)
    await check_http_status(resp)

    if not media_item.is_segment and (content_type := _get_content_type(resp.headers)):
        _check_content_type(content_type, media_item.ext)

    _check_for_placeholder_files(resp.headers)

    if resp.status != HTTPStatus.PARTIAL_CONTENT and resume_point:
        logger.warning(
            "Deleting partial file '%s'. Server did not acknowledge byte-range request",
            media_item.partial_file,
        )
        await aio.unlink(media_item.partial_file)


def resolve_download_dir(download_folder: Path, config: Config) -> Path:
    if config.subfolders.create or USE_RETRY_PATH.get():
        return download_folder

    while download_folder.parent != config.download_folder:
        download_folder = download_folder.parent

    return download_folder
