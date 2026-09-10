from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Self, final

import xxhash

from cyberdrop_dl import aio
from cyberdrop_dl.constants import TempExt
from cyberdrop_dl.progress.hashing import HashingStats, HashingUI
from cyberdrop_dl.progress.scraping import show_msg
from cyberdrop_dl.signature import simple_repr

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyberdrop_dl.config import Config
    from cyberdrop_dl.database._db import Database
    from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem

logger = logging.getLogger(__name__)

FileHashes = dict[str, dict[int, set[Path]]]

type HashAlgoLiteral = Literal["md5", "xxh128", "sha256"]


class HashAlgo(StrEnum):
    MD5 = "md5"
    XXH128 = "xxh128"
    SHA256 = "sha256"

    if TYPE_CHECKING:
        value: HashAlgoLiteral  # pyright: ignore[reportIncompatibleMethodOverride]


_HASHERS: Final = {
    HashAlgo.MD5: hashlib.md5,
    HashAlgo.XXH128: xxhash.xxh128,
    HashAlgo.SHA256: hashlib.sha256,
}
_CHUNK_SIZE: Final = 1024 * 1024  # 1MB
_CONCURRENCY: Final = 10


def _compute_hash(file: Path, algorithm: HashAlgo | HashAlgoLiteral, shutdown: threading.Event | None = None) -> str:
    hasher = _HASHERS[HashAlgo(algorithm)]()
    with file.open("rb") as fp:
        buffer = bytearray(_CHUNK_SIZE)
        mem_view = memoryview(buffer)
        while size := fp.readinto(buffer):
            if shutdown and shutdown.is_set():
                raise RuntimeError("Hasher shutting down")
            hasher.update(mem_view[:size])

    return hasher.hexdigest()


async def hash_directory(hasher: Hasher) -> HashingStats:
    if not await aio.is_dir(hasher.path):
        raise NotADirectoryError(None, hasher.path)

    async with hasher.database:
        with hasher.tui():
            async with asyncio.TaskGroup() as tg:
                async for file in aio.rglob(hasher.path, "*"):
                    _ = tg.create_task(hasher.update_db_and_retrive_hash(file))

    return hasher.stats


@final
class Hasher:
    def __init__(self, hashes: Iterable[HashAlgo | HashAlgoLiteral], database: Database, path: Path) -> None:
        self.path = path
        self.hashes: tuple[HashAlgo, ...] = tuple(sorted(set(map(HashAlgo, hashes)) | {HashAlgo.XXH128}))
        self.database = database
        self.tui = HashingUI(path)
        self._cwd = Path.cwd().resolve().absolute()
        self._hashes_map: FileHashes = defaultdict(lambda: defaultdict(set))
        self._sem = asyncio.BoundedSemaphore(_CONCURRENCY)
        self._hashed_items: set[tuple[str, ...]] = set()
        self._pool = ThreadPoolExecutor(max_workers=_CONCURRENCY * len(self.hashes), thread_name_prefix="hashing")
        self._shutdown = threading.Event()

    __repr__ = simple_repr("path", "hashes", "database")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_) -> None:
        self._shutdown.set()
        self._pool.shutdown(wait=True)

    @classmethod
    def create(cls, config: Config, db: Database, path: Path | None = None) -> Self:
        return cls(
            config.hashing.extra_hashes,
            db,
            path=(path or config.download_folder).expanduser().resolve().absolute(),
        )

    @property
    def stats(self) -> HashingStats:
        return self.tui.stats

    async def hash_file(self, filename: Path | str, hash_type: HashAlgoLiteral) -> str:
        file_path = self._cwd / filename
        return await asyncio.get_running_loop().run_in_executor(
            self._pool,
            _compute_hash,
            file_path,
            hash_type,
            self._shutdown,
        )

    async def hash_item(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return
        hash_value = await self.update_db_and_retrive_hash(
            media_item.path,
            media_item.original_filename,
            referer=media_item.referer,
        )
        await self.save_hash_data(media_item, hash_value)

    async def update_db_and_retrive_hash(
        self,
        file: Path | str,
        original_filename: str | None = None,
        referer: AbsoluteHttpURL | None = None,
    ) -> str | None:
        file = Path(file)

        if file.suffix in TempExt:
            return None

        try:
            if not await aio.get_size(file):
                return None
        except IsADirectoryError:
            return None

        async with self._sem:
            with self.tui.new_file(file):
                async with asyncio.TaskGroup() as tg:
                    logger.info("Computing hashes of '%s'", file)
                    task_map = {
                        algo: tg.create_task(
                            self._update_db_and_retrive_hash(
                                file,
                                original_filename,
                                referer,
                                algo.value,
                            )
                        )
                        for algo in self.hashes
                    }

            hashes = {algo: result for algo, task in task_map.items() if (result := task.result()) is not None}
            logger.debug("Hashes of '%s'\n%s", file, hashes)

        return hashes.get(HashAlgo.XXH128)

    async def _update_db_and_retrive_hash(
        self,
        file: Path,
        original_filename: str | None,
        referer: AbsoluteHttpURL | None,
        hash_type: HashAlgoLiteral,
    ) -> str | None:
        """Generates hash of a file."""

        hash_value = await self.database.hash.get_file_hash_exists(file, hash_type)
        try:
            if not hash_value:
                hash_value = await self.hash_file(file, hash_type)
                await self.database.hash.insert_or_update_hash_db(
                    hash_value,
                    hash_type,
                    file,
                    original_filename,
                    referer,
                )
                self.tui.add_completed(hash_type)
            else:
                self.tui.stats.prev_hashed += 1
                await self.database.hash.insert_or_update_hash_db(
                    hash_value,
                    hash_type,
                    file,
                    original_filename,
                    referer,
                )
        except Exception:
            logger.exception("Error computing %s hash of '%s'", hash_type, file)
        else:
            return hash_value

    async def save_hash_data(self, media_item: MediaItem, hash_value: str | None) -> None:
        if not hash_value:
            return

        absolute_path = await aio.resolve(media_item.path)
        size = await aio.get_size(media_item.path)
        assert size
        if hash_value:
            media_item.xxhash = hash_value
        self._hashes_map[hash_value][size].add(absolute_path)
        self._hashed_items.add(media_item.id)

    async def run(self, downloads: Iterable[MediaItem]) -> FileHashes:
        with self.tui():
            return await self._get_file_hashes_dict(downloads)

    async def _get_file_hashes_dict(self, downloads: Iterable[MediaItem]) -> FileHashes:

        results = await aio.gather(*(_exists(item) for item in downloads if item.id not in self._hashed_items))
        for media_item in results:
            if media_item is None:
                continue
            try:
                await self.hash_item(media_item)
            except Exception:
                logger.exception(msg=f"Unable to hash '{media_item.path}'")
        return self._hashes_map


async def _exists(item: MediaItem) -> MediaItem | None:
    if await aio.is_file(item.path):
        return item


async def compute_in_place_hash(hasher: Hasher, media_item: MediaItem) -> None:
    try:
        with show_msg(f"Hashing {media_item.path.name}"):
            assert media_item.original_filename
            hash_value = await hasher.update_db_and_retrive_hash(
                media_item.path, media_item.original_filename, media_item.referer
            )
            await hasher.save_hash_data(media_item, hash_value)
    except Exception:
        logger.exception("After hash processing failed: '%s'", media_item.path)
