from __future__ import annotations

import asyncio
import dataclasses
import itertools
import logging
from contextvars import ContextVar
from http import HTTPStatus
from typing import TYPE_CHECKING, NamedTuple, Protocol

from cyberdrop_dl import aio, constants, ffmpeg
from cyberdrop_dl.exceptions import DownloadError
from cyberdrop_dl.utils import parse_url
from cyberdrop_dl.utils.crypto import aes_cbc_decrypt, aes_unpad
from cyberdrop_dl.utils.m3u8 import HLSKey

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable, Sequence
    from pathlib import Path

    from m3u8.model import InitializationSection, Segment

    from cyberdrop_dl.clients.http import HTTPClient
    from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem
    from cyberdrop_dl.utils.m3u8 import M3U8, Rendition

    DownloadFn = Callable[[MediaItem], Awaitable[bool]]


logger = logging.getLogger(__name__)

CONCURRENT_SEGMENTS: ContextVar[int] = ContextVar("CONCURRENT_SEGMENTS")
_DECRYPTER: ContextVar[AESHLSDecrypter] = ContextVar("_DECRYPTER")


class Streams(NamedTuple):
    video: Path
    audio: Path | None
    subs: Path | None


class HLSSegment(NamedTuple):
    idx: int
    name: str
    url: AbsoluteHttpURL
    decrypt_info: HLSKey | None = None


class HLSDecrypter(Protocol):
    async def __call__(self, content: bytes, key: HLSKey) -> bytes: ...


@dataclasses.dataclass(slots=True, frozen=True)
class AESHLSDecrypter(HLSDecrypter):
    client: HTTPClient
    _lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    _cache: dict[AbsoluteHttpURL, bytes] = dataclasses.field(default_factory=dict)

    async def get_key(self, uri: AbsoluteHttpURL, headers: dict[str, str] | None = None) -> bytes:
        if aes_key := self._cache.get(uri):
            return aes_key

        async with self._lock:
            if aes_key := self._cache.get(uri):
                return aes_key

            async with self.client.raw_request(uri, headers=headers or {}) as resp:
                aes_key = self._cache[uri] = await resp.read()

            return aes_key

    async def __call__(self, content: bytes, key: HLSKey, headers: dict[str, str] | None = None) -> bytes:
        aes_key = await self.get_key(key.uri, headers=headers)
        return aes_unpad(aes_cbc_decrypt(content, aes_key, key.iv))


def _create_segments(segments: Iterable[Segment | InitializationSection], count: int) -> Generator[HLSSegment]:
    padding = max(5, len(str(count)))
    for index, segment in enumerate(segments, 1):
        assert segment.uri
        yield HLSSegment(
            idx=index - 1,
            name=f"{index:0{padding}d}{constants.TempExt.HLS}",
            url=parse_url(segment.absolute_uri, trim=False),
            decrypt_info=HLSKey.parse(segment),
        )


def _create_media_segment(media_item: MediaItem, segment: HLSSegment, download_folder: Path) -> MediaItem:
    # TODO: segments download should bypass the downloads slots limits.
    # They count as a single download

    new_item = media_item.as_segment(segment.name, segment.url)
    new_item.download_folder = download_folder
    if segment.decrypt_info:
        segment.decrypt_info(new_item.extra_info)

    return new_item


def _create_media_segments(m3u8: M3U8, temp_dir: Path, item: MediaItem) -> Generator[MediaItem]:
    assert m3u8.media_type
    out_folder = temp_dir / m3u8.media_type
    for segment in _create_segments(itertools.chain(m3u8.segment_map, m3u8.segments), count=m3u8.total_segments):
        yield _create_media_segment(item, segment, out_folder)


def _check_segments(m3u8: M3U8) -> None:
    if m3u8.total_segments == 0:
        msg = f"{m3u8.media_type} m3u8 manifest ({m3u8.source}) has no valid segments"
        raise DownloadError(HTTPStatus.NO_CONTENT, msg)


async def _download_m3u8(
    m3u8: M3U8,
    temp_dir: Path,
    item: MediaItem,
    download_fn: DownloadFn,
    sem: asyncio.BoundedSemaphore,
) -> Path:
    assert m3u8.media_type
    _check_segments(m3u8)
    output = _prepare_output_path(m3u8, item.path)
    if await aio.is_file(output):
        return output

    logger.debug(
        "Starting HLS download (%s, %s segments) for %s (%s)",
        m3u8.media_type,
        f"{m3u8.total_segments:,}",
        item.real_url,
        m3u8.source,
    )

    m_segments = await _download_segments(
        _create_media_segments(m3u8, temp_dir, item),
        m3u8.total_segments,
        download_fn,
        sem,
    )
    await _decrypt_segments(m_segments, sem)
    await _merge_segments(m_segments, output)
    return output


async def _decrypt_segments(items: Iterable[MediaItem], sem: asyncio.BoundedSemaphore) -> None:
    decrypter = _DECRYPTER.get()

    async def decrypt(item: MediaItem) -> None:
        if key := HLSKey.get(item.extra_info):
            logger.debug("Decrypting '%s' with %s", item.path, key)
            content = await decrypter(await aio.read_bytes(item.path), key, item.headers)
            await aio.write_bytes(item.path, content)

    await aio.map(decrypt, items, task_limit=sem)


async def _download_segments(
    segments: Iterable[MediaItem],
    count: int,
    download_fn: Callable[[MediaItem], Awaitable[bool]],
    sem: asyncio.BoundedSemaphore,
) -> list[MediaItem]:

    async def download(seg_media_item: MediaItem) -> MediaItem | None:
        if await download_fn(seg_media_item):
            return seg_media_item

    results = await aio.map(
        download,
        segments,
        task_limit=sem,
    )

    results = [item for item in results if item is not None]
    if len(results) != count:
        msg = f"Download of some segments failed. Successful: {len(results):,}/{count:,} "
        raise DownloadError("HLS Seg Error", msg)

    return results


async def _merge_segments(results: Sequence[MediaItem], output: Path) -> None:
    if len(results) == 1:
        await aio.move(results[0].path, output)
    else:
        await ffmpeg.raw_concat([item.path for item in results], output)


def _prepare_output_path(m3u8: M3U8, output: Path) -> Path:
    real_ext = parse_url(m3u8.segments[0].absolute_uri).suffix
    if len(m3u8.segments) > 1:
        suffix = f".{m3u8.media_type}{real_ext}" if m3u8.media_type == "subtitle" else f".{m3u8.media_type}.ts"
    else:
        suffix = output.suffix + real_ext

    return output.with_suffix(suffix)


async def download(media_item: MediaItem, rendition: Rendition, download_fn: DownloadFn, client: HTTPClient) -> Streams:
    """Download a rendition group"""
    temp_dir = media_item.path.with_suffix(constants.TempExt.HLS)

    sem = asyncio.BoundedSemaphore(CONCURRENT_SEGMENTS.get())

    async def download(m3u8: M3U8) -> Path:
        _DECRYPTER.set(AESHLSDecrypter(client))
        return await _download_m3u8(m3u8, temp_dir, media_item, download_fn, sem)

    async def download_subs() -> Path | None:
        if not rendition.subtitle:
            return None
        try:
            subs = await download(rendition.subtitle)
        except Exception:
            logger.exception("Unable to download subtitles for %s, Skipping", media_item.url)
        else:
            logger.warning(
                "Found subtitles for %s, but CDL is currently unable to merge them. Subtitles were saved at '%s'",
                media_item.url,
                subs,
            )
            return subs

    async def download_audio() -> Path | None:
        if rendition.audio:
            return await download(rendition.audio)

    async with asyncio.TaskGroup() as tg:
        # Keep this priority for the semaphore: subs > audio > video
        subs = tg.create_task(download_subs())
        audio = tg.create_task(download_audio())
        video = tg.create_task(download(rendition.video))

    try:
        await aio.rmdir(temp_dir)
    except OSError:
        pass

    return Streams(video.result(), audio.result(), subs.result())
