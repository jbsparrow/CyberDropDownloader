from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Mapping
from hashlib import md5 as md5_hasher
from hashlib import sha256 as sha256_hasher
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Protocol

import aiofiles
from send2trash import send2trash
from xxhash import xxh128 as xxh128_hasher

from cyberdrop_dl.constants import Hashing
from cyberdrop_dl.types import AbsoluteHttpURL, Hash, HashAlgorithm
from cyberdrop_dl.ui.prompts.basic_prompts import enter_to_continue
from cyberdrop_dl.utils.database.tables import hash_table
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import get_size_or_none

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.config_definitions.config_settings import DupeCleanup
    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.ui.progress.hash_progress import HashProgress

_CHUNK_SIZE = 1024 * 1024 * 5  # 5MB
_DedupeMapping = Mapping[Hash, Mapping[int, set[Path]]]


class _Hasher(Protocol):
    def hexdigest(self) -> str: ...
    def update(self, obj: bytes, /) -> None: ...


_HASHER_MAP: dict[str, Callable[[], _Hasher]] = {
    HashAlgorithm.xxh128: xxh128_hasher,
    HashAlgorithm.md5: md5_hasher,
    HashAlgorithm.sha256: sha256_hasher,
}


class _Hashable(NamedTuple):
    file: Path
    original_filename: str | None = None
    referer: AbsoluteHttpURL | None = None


_semaphore = asyncio.Semaphore(4)


class HashManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.hashed_media_items: set[MediaItem] = set()
        self.hashes_dict: _DedupeMapping = defaultdict(lambda: defaultdict(set))

    @property
    def dupe_cleanup_options(self) -> DupeCleanup:
        return self.manager.config_manager.settings_data.dupe_cleanup_options

    @property
    def progress(self) -> HashProgress:
        return self.manager.progress_manager.hash_progress

    async def hash_directory(self, path: Path) -> None:
        with self.manager.live_manager.get_hash_live(stop=True):
            if not await asyncio.to_thread(path.is_dir):
                raise NotADirectoryError
            for file in path.rglob("*"):
                _ = await self.get_xxh128_hash(_Hashable(file))

    async def hash_item_during_download(self, media_item: MediaItem) -> None:
        if self.dupe_cleanup_options.hashing != Hashing.IN_PLACE:
            return

        await self.manager.states.RUNNING.wait()
        await self.hash_item(media_item)

    async def hash_item(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return

        source = _Hashable(media_item.complete_file, media_item.original_filename, media_item.referer)
        if hash_value := await self.get_xxh128_hash(source):
            size = await asyncio.to_thread(get_size_or_none, media_item.complete_file)
            assert size
            self.hashed_media_items.add(media_item)
            media_item.hash = hash_value
            self.hashes_dict[hash_value][size].add(media_item.complete_file)

    async def get_xxh128_hash(self, source: _Hashable) -> Hash | None:
        if source.file.suffix == ".part":
            return
        if not await asyncio.to_thread(get_size_or_none, source.file):
            return

        xxh128_hash = None
        for hash_type in self.dupe_cleanup_options.algorithms_to_use:
            try:
                hash = await self._get_hash(source, hash_type)
                if hash_type == HashAlgorithm.xxh128:
                    xxh128_hash = hash
            except Exception as e:
                log(f"Error hashing '{source}': {e}", 40, exc_info=True)
        return xxh128_hash

    async def _get_hash(self, source: _Hashable, hash_type: HashAlgorithm) -> Hash:
        self.progress.update_currently_hashing(source.file)
        hash_value = await hash_table.get_file_hash_if_exists(source.file, hash_type)
        if hash_value:
            self.progress.add_prev_hash()
        else:
            hash_value = await compute_file_hash(source.file, hash_type)
            self.progress.add_new_completed_hash()

        hash = Hash(hash_type, hash_value)
        await hash_table.insert_or_update_hash_db(*source, hash)
        return hash

    async def cleanup_dupes_after_download(self) -> None:
        if self.dupe_cleanup_options.hashing == Hashing.OFF:
            return
        if not self.dupe_cleanup_options.auto_dedupe:
            return
        if self.manager.config_manager.settings_data.runtime_options.ignore_history:
            return
        with self.manager.live_manager.get_hash_live(stop=True):
            file_hashes_dict = await self.get_file_hashes_dict()
        with self.manager.live_manager.get_remove_file_via_hash_live(stop=True):
            await self.final_dupe_cleanup(file_hashes_dict)

    async def final_dupe_cleanup(self, final_dict: _DedupeMapping) -> None:
        """cleanup files based on dedupe setting"""
        log("Starting autodedupe...")
        tasks = []
        for hash, size_dict in final_dict.items():
            for size in size_dict:
                original_file: Path | None = None
                async for db_match in hash_table.get_files_with_hash_matches(hash, size):
                    if not original_file:
                        original_file = db_match
                        continue

                    tasks.append(self.delete_and_log(db_match, hash, original_file))

        if tasks:
            await asyncio.gather(*tasks)
        log("Finished autodedupe")

    async def delete_and_log(self, file: Path, hash: Hash, original_file: Path) -> None:
        to_trash = self.dupe_cleanup_options.send_deleted_to_trash
        suffix = "Sent to trash " if to_trash else "Permanently deleted"
        reason = "duplicate of file downloaded before"
        try:
            deleted = await delete_file(file, to_trash)
            if deleted:
                msg = (
                    f"Removed [{suffix}]: '{file}'"
                    f" -> Reason: {reason}\n"
                    f" -> Original file: '{original_file}'\n"
                    f" -> Hash: {hash.hash_string} "
                    ""
                )

                log(msg, 10)
                self.progress.add_removed_file()
                await self.manager.log_manager.write_dedupe_log(original_file, hash.value, file)

        except OSError as e:
            log(f"Unable to remove '{file}' with hash {hash.hash_string}: {e}", 40)

    async def get_file_hashes_dict(self) -> _DedupeMapping:
        """Get a dictionary of files based on matching file hashes and file size."""
        downloads = self.manager.path_manager.completed_downloads - self.hashed_media_items

        async def exists(item: MediaItem) -> MediaItem | None:
            if await asyncio.to_thread(item.complete_file.is_file):
                return item

        results = await asyncio.gather(*(exists(item) for item in downloads))
        for media_item in results:
            if media_item is None:
                continue
            try:
                await self.hash_item(media_item)
            except Exception as e:
                msg = f"Unable to hash file = {media_item.complete_file}: {e}"
                log(msg, 40)
        return self.hashes_dict


async def delete_file(path: Path, to_trash: bool = True) -> bool:
    """Deletes a file and return `True` on success, `False` is the file was not found.

    Any other exception is propagated"""

    if to_trash:
        coro = asyncio.to_thread(send2trash, path)
    else:
        coro = asyncio.to_thread(path.unlink)

    try:
        await coro
    except FileNotFoundError:
        pass
    except OSError as e:
        # send2trash raises everything as a bare OSError. We should only ignore FileNotFound and raise everything else
        if "File not found" not in str(e):
            raise
    else:
        return True

    return False


def hash_directory_scanner(manager: Manager, path: Path) -> None:
    async def hash_directory() -> None:
        start_time = time.perf_counter()
        try:
            await manager.async_db_hash_startup()
            await manager.hash_manager.hash_directory(path)
            manager.progress_manager.print_stats(start_time)
        finally:
            await manager.async_db_close()

    asyncio.run(hash_directory())
    enter_to_continue()


async def compute_file_hash(file: Path, hash_type: HashAlgorithm) -> Hash:
    """Calculates the hash of a file asynchronously.

    :param filename: The path to the file to hash.
    :param hash_type: The type of hash to calculate (e.g., MD5, SHA1, xxH128).
    :return: The calculated hash value as a HashValue object.
    """
    file_path = Path.cwd() / file
    async with _semaphore, aiofiles.open(file_path, "rb") as file_io:
        data = await file_io.read(_CHUNK_SIZE)
        current_hasher = _HASHER_MAP[hash_type]()
        while data:
            await asyncio.to_thread(current_hasher.update, data)
            data = await file_io.read(_CHUNK_SIZE)
        return Hash(hash_type, current_hasher.hexdigest())
