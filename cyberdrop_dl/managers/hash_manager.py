from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Generator, Mapping
from hashlib import md5 as md5_hasher
from hashlib import sha256 as sha256_hasher
from pathlib import Path
from typing import TYPE_CHECKING, NewType, Protocol

import aiofiles
from send2trash import send2trash
from typing_extensions import Buffer

from cyberdrop_dl.ui.prompts.basic_prompts import enter_to_continue
from cyberdrop_dl.utils.constants import Hashing, HashType
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import get_size_or_none

try:
    from xxhash import xxh128 as xxhasher
except ImportError:
    xxhasher = None


if TYPE_CHECKING:
    from collections.abc import Callable

    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


HashValue = NewType("HashValue", str)
Xxh128HashValue = NewType("Xxh128HashValue", HashValue)
DedupeMapping = Mapping[str, Mapping[int, set[Path]]]


class Hasher(Protocol):
    def hexdigest(self) -> str: ...
    def update(self, obj: Buffer, /) -> None: ...


HASHER_MAP: dict[str, Callable[..., Hasher]] = {
    HashType.xxh128: xxhasher,  # type: ignore
    HashType.md5: md5_hasher,
    HashType.sha256: sha256_hasher,
}


class HashManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.hashed_media_items: set[MediaItem] = set()
        self.hashes_dict: DedupeMapping = defaultdict(lambda: defaultdict(set))

    def _hashers_to_use(self) -> Generator[HashType]:
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_md5_hash:
            yield HashType.md5
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_sha256_hash:
            yield HashType.sha256
        yield HashType.xxh128

    async def hash_file(self, filename: Path, hash_type: HashType) -> str:
        file_path = Path.cwd() / filename
        async with aiofiles.open(file_path, "rb") as file_io:
            CHUNK_SIZE = 1024 * 1024  # 1MB
            filedata = await file_io.read(CHUNK_SIZE)
            if hash_type == HashType.xxh128 and not xxhasher:
                raise RuntimeError("xxhash module is not installed")
            current_hasher = HASHER_MAP[hash_type]()
            while filedata:
                current_hasher.update(filedata)
                filedata = await file_io.read(CHUNK_SIZE)
            return current_hasher.hexdigest()

    async def hash_directory(self, path: Path) -> None:
        with self.manager.live_manager.get_hash_live(stop=True):
            if not await asyncio.to_thread(path.is_dir):
                raise NotADirectoryError
            for file in path.rglob("*"):
                await self.hash_and_update_db(file)

    async def hash_item(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return

        if hash := await self.hash_and_update_db(*get_hash_props(media_item)):
            size = await asyncio.to_thread(get_size_or_none, media_item.complete_file)
            assert size
            self.hashed_media_items.add(media_item)
            media_item.hash = hash
            self.hashes_dict[hash][size].add(media_item.complete_file)

    async def hash_item_during_download(self, media_item: MediaItem) -> None:
        if self.manager.config_manager.settings_data.dupe_cleanup_options.hashing != Hashing.IN_PLACE:
            return

        await self.manager.states.RUNNING.wait()
        await self.hash_item(media_item)

    async def hash_and_update_db(
        self, file: Path, original_filename: str | None = None, referer: URL | None = None
    ) -> Xxh128HashValue | None:
        if file.suffix == ".part":
            return

        if not await asyncio.to_thread(get_size_or_none, file):
            return

        for hash_type in self._hashers_to_use():
            try:
                hash = await self._hash_and_update_db(file, original_filename, referer, hash_type)
                if hash_type == HashType.xxh128:
                    return Xxh128HashValue(hash)
            except Exception as e:
                log(f"Error hashing {file} : {e}", 40, exc_info=True)

    async def _hash_and_update_db(
        self, file: Path, original_filename: str | None, referer: URL | None, hash_type: HashType
    ) -> HashValue:
        """Generates hash of a file."""
        self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        hash = await self.manager.db_manager.hash_table.get_file_hash_exists(file, hash_type)
        if hash:
            self.manager.progress_manager.hash_progress.add_prev_hash()
        else:
            hash = await self.manager.hash_manager.hash_file(file, hash_type)
            self.manager.progress_manager.hash_progress.add_new_completed_hash()

        await self.manager.db_manager.hash_table.insert_or_update_hash_db(
            file, original_filename, referer, hash_type, hash
        )

        return HashValue(hash)

    async def cleanup_dupes_after_download(self) -> None:
        if self.manager.config_manager.settings_data.dupe_cleanup_options.hashing == Hashing.OFF:
            return
        if not self.manager.config_manager.settings_data.dupe_cleanup_options.auto_dedupe:
            return
        if self.manager.config_manager.settings_data.runtime_options.ignore_history:
            return
        with self.manager.live_manager.get_hash_live(stop=True):
            file_hashes_dict = await self.get_file_hashes_dict()
        with self.manager.live_manager.get_remove_file_via_hash_live(stop=True):
            await self.final_dupe_cleanup(file_hashes_dict)

    async def final_dupe_cleanup(self, final_dict: DedupeMapping) -> None:
        """cleanup files based on dedupe setting"""
        to_trash = self.manager.config_manager.settings_data.dupe_cleanup_options.send_deleted_to_trash
        suffix = "Sent to trash " if to_trash else "Permanently deleted"
        log("Starting autodedupe...")

        async def delete_and_log(file: Path) -> None:
            nonlocal hash, suffix, og_file
            reason = "duplicate of file downloaded before"
            try:
                deleted = await delete_file(file, to_trash)
                if deleted:
                    msg = (
                        f"Removed [{suffix}]: '{file}'"
                        f" -> Reason: {reason}\n"
                        f" -> Original file: '{og_file}'\n"
                        f" -> xxh128 hash: {hash} "
                        ""
                    )

                    log(msg, 10)
                    self.manager.progress_manager.hash_progress.add_removed_file()
                    await self.manager.log_manager.write_dedupe_log(og_file, hash, file)

            except OSError as e:
                log(f"Unable to remove '{file}' with hash {hash}: {e}", 40)

        tasks = []
        get_matches = self.manager.db_manager.hash_table.get_files_with_hash_matches
        for hash, size_dict in final_dict.items():
            for size in size_dict:
                db_matches = await get_matches(hash, size, HashType.xxh128)
                if not db_matches or len(db_matches) < 2:
                    continue
                og_file = file = Path(*db_matches[0][:2])
                for match in db_matches[1:]:
                    file = Path(*match[:2])
                    tasks.append(delete_and_log(file))

        await asyncio.gather(*tasks)
        log("Finished autodedupe")

    async def get_file_hashes_dict(self) -> DedupeMapping:
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


def get_hash_props(media_item: MediaItem) -> tuple[Path, str | None, URL]:
    return media_item.complete_file, media_item.original_filename, media_item.referer


def hash_directory_scanner(manager: Manager, path: Path) -> None:
    async def hash_directory():
        start_time = time.perf_counter()
        try:
            await manager.async_db_hash_startup()
            await manager.hash_manager.hash_directory(path)
            manager.progress_manager.print_stats(start_time)
        finally:
            await manager.async_db_close()

    asyncio.run(hash_directory())
    enter_to_continue()
