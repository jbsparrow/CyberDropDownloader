from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from send2trash import send2trash

from cyberdrop_dl.data_structures.hash import HashAlgo, Hashing
from cyberdrop_dl.ui.prompts.basic_prompts import enter_to_continue
from cyberdrop_dl.utils import aio
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.config.config_model import DupeCleanup
    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager


def hash_directory_scanner(manager: Manager, path: Path) -> None:
    async def run() -> None:
        await manager.async_db_hash_startup()
        await manager.hash_manager.hash_client.hash_directory(path)
        manager.progress_manager.print_dedupe_stats()
        await manager.async_db_close()

    asyncio.run(run())
    enter_to_continue()


class HashClient:
    """Manage hashes and db insertion."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self._hashed_items: set[MediaItem] = set()
        self._hashes_map: dict[str, dict[int, set[Path]]] = defaultdict(lambda: defaultdict(set))

    @property
    def dupe_cleanup_options(self) -> DupeCleanup:
        return self.manager.config.dupe_cleanup_options

    @property
    def disabled(self) -> bool:
        return (
            (self.dupe_cleanup_options.hashing == Hashing.OFF)
            or self.manager.config.runtime_options.ignore_history
            or not self.dupe_cleanup_options.auto_dedupe
        )

    async def hash_directory(self, path: Path) -> None:
        if not await asyncio.to_thread(path.is_dir):
            raise NotADirectoryError
        with self.manager.live_manager.get_hash_live(stop=True):
            coros = [self._hash_file(file) for file in path.rglob("*")]
            await aio.gather(coros, 100)

    async def _hash_item(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return
        hash_value = await self._hash_file(media_item.complete_file, media_item.original_filename, media_item.referer)
        await self._update_hashes_map(media_item, hash_value)

    async def hash_item_during_download(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return

        if self.dupe_cleanup_options.hashing != Hashing.IN_PLACE:
            return

        await self.manager.states.RUNNING.wait()
        assert media_item.original_filename
        hash = await self._hash_file(media_item.complete_file, media_item.original_filename, media_item.referer)
        await self._update_hashes_map(media_item, hash)

    async def _hash_file(
        self,
        file: Path,
        original_filename: str | None = None,
        referer: URL | None = None,
    ) -> str | None:
        if file.suffix in (".part", ".cdl_hls"):
            return

        if not await aio.get_size(file):
            return

        async def get_hash(hash_type: HashAlgo) -> str | None:
            try:
                return await self._get_or_compute_hash(file, original_filename, referer, hash_type)
            except Exception as e:
                log(f"Error hashing '{file}' : {e}", 40, exc_info=True)

        other_hashes = []
        if self.dupe_cleanup_options.add_md5_hash:
            other_hashes.append(get_hash(HashAlgo.md5))

        if self.dupe_cleanup_options.add_sha256_hash:
            other_hashes.append(get_hash(HashAlgo.sha256))

        if other_hashes:
            await asyncio.gather(*other_hashes)

        return await get_hash(HashAlgo.xxh128)

    async def _get_or_compute_hash(
        self,
        file: Path,
        original_filename: str | None,
        referer: URL | None,
        hash_type: HashAlgo,
    ) -> str:
        """Generates hash of a file."""
        self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        existing_hash_value = await self.manager.db_manager.hash_table.get_hash_value(file, hash_type)

        async def update_db(hash_value: str) -> None:
            await self.manager.db_manager.hash_table.insert_or_update_hash_db(
                hash_value,
                hash_type,
                file,
                original_filename,
                referer,
            )

        if existing_hash_value:
            self.manager.progress_manager.hash_progress.add_prev_hash()
            await update_db(existing_hash_value)
            return existing_hash_value

        hash_value = await self.manager.hash_manager.compute_hash(file, hash_type)
        await update_db(hash_value)
        self.manager.progress_manager.hash_progress.add_new_completed_hash()
        return hash_value

    async def _update_hashes_map(self, media_item: MediaItem, hash_value: str | None) -> None:
        if not hash_value:
            return

        assert media_item.complete_file.is_absolute()
        size = await aio.get_size(media_item.complete_file)
        assert size
        self._hashed_items.add(media_item)
        if hash_value:
            media_item.hash = hash_value
        self._hashes_map[hash_value][size].add(media_item.complete_file)

    async def cleanup_dupes_after_download(self) -> None:
        if self.disabled:
            return

        with self.manager.live_manager.get_hash_live(stop=True):
            await self._sync_hashes_map()

        with self.manager.live_manager.get_remove_file_via_hash_live(stop=True):
            await self._final_dupe_cleanup()

    async def _final_dupe_cleanup(self) -> None:
        """cleanup files based on dedupe setting"""
        get_matches = self.manager.db_manager.hash_table.get_files_by_matching_hash
        to_trash = self.dupe_cleanup_options.send_deleted_to_trash
        suffix = "Sent to trash " if to_trash else "Permanently deleted"

        async def delete_and_log(file: Path, hash_value: str) -> None:
            try:
                deleted = await _delete_file(file, to_trash)
                if deleted:
                    msg = f"Removed new download '{file}' with hash {hash_value} [{suffix}]"
                    log(msg, 10)
                    self.manager.progress_manager.hash_progress.add_removed_file()

            except OSError as e:
                log(f"Unable to remove '{file}' with hash {hash_value}: {e}", 40)

        async with asyncio.TaskGroup() as tg:

            async def delete_dupes(hash_value: str, size: int) -> None:
                db_matches = await get_matches(hash_value, size, HashAlgo.xxh128)
                for row in db_matches[1:]:
                    file = Path(row["folder"], row["download_filename"])
                    tg.create_task(delete_and_log(file, hash_value))

            for hash_value, size_dict in self._hashes_map.items():
                for size in size_dict:
                    tg.create_task(delete_dupes(hash_value, size))

    async def _sync_hashes_map(self) -> None:
        """Makes sures all downloaded files are in the internal hashes map"""
        downloads = self.manager.path_manager.completed_downloads - self._hashed_items

        async def exists(item: MediaItem) -> MediaItem | None:
            if await aio.get_size(item.complete_file):
                return item

        async with asyncio.TaskGroup() as tg:
            for result in asyncio.as_completed([exists(item) for item in downloads]):
                media_item = await result
                if media_item is not None:
                    tg.create_task(self._hash_item(media_item))


async def _delete_file(path: Path, to_trash: bool = True) -> bool:
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
        msg = str(e)
        if "File not found" not in msg:
            raise
    else:
        return True

    return False
