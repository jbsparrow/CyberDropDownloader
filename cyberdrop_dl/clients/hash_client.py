from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles.os
from send2trash import send2trash

from cyberdrop_dl.data_structures.hash import Hashing
from cyberdrop_dl.ui.prompts.basic_prompts import enter_to_continue
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import get_size_or_none

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager


def hash_directory_scanner(manager: Manager, path: Path) -> None:
    asyncio.run(_hash_directory_scanner_helper(manager, path))
    enter_to_continue()


async def _hash_directory_scanner_helper(manager: Manager, path: Path) -> None:
    await manager.async_db_hash_startup()
    await manager.hash_manager.hash_client.hash_directory(path)
    manager.progress_manager.print_dedupe_stats()
    await manager.async_db_close()


class HashClient:
    """Manage hashes and db insertion."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.xxhash = "xxh128"
        self.md5 = "md5"
        self.sha256 = "sha256"
        self.hashed_media_items: set[MediaItem] = set()
        self.hashes_dict: defaultdict[str, defaultdict[int, set[Path]]] = defaultdict(lambda: defaultdict(set))

    async def startup(self) -> None:
        pass

    async def hash_directory(self, path: Path) -> None:
        path = Path(path)
        with self.manager.live_manager.get_hash_live(stop=True):
            if not await asyncio.to_thread(path.is_dir):
                raise NotADirectoryError
            for file in path.rglob("*"):
                await self.update_db_and_retrive_hash(file)

    async def hash_item(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return
        hash = await self.update_db_and_retrive_hash(
            media_item.complete_file, media_item.original_filename, media_item.referer
        )
        await self.save_hash_data(media_item, hash)

    async def hash_item_during_download(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return
        if self.manager.config_manager.settings_data.dupe_cleanup_options.hashing != Hashing.IN_PLACE:
            return
        await self.manager.states.RUNNING.wait()
        try:
            assert media_item.original_filename
            hash = await self.update_db_and_retrive_hash(
                media_item.complete_file, media_item.original_filename, media_item.referer
            )
            await self.save_hash_data(media_item, hash)
        except Exception as e:
            log(f"After hash processing failed: '{media_item.complete_file}' with error {e}", 40, exc_info=True)

    async def update_db_and_retrive_hash(
        self, file: Path | str, original_filename: str | None = None, referer: URL | None = None
    ) -> str | None:
        file = Path(file)
        if file.suffix == ".part":
            return
        if not await asyncio.to_thread(get_size_or_none, file):
            return
        hash = await self._update_db_and_retrive_hash_helper(file, original_filename, referer, hash_type=self.xxhash)
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_md5_hash:
            await self._update_db_and_retrive_hash_helper(file, original_filename, referer, hash_type=self.md5)
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_sha256_hash:
            await self._update_db_and_retrive_hash_helper(file, original_filename, referer, hash_type=self.sha256)
        return hash

    async def _update_db_and_retrive_hash_helper(
        self,
        file: Path | str,
        original_filename: str | None,
        referer: URL | None,
        hash_type: str,
    ) -> str | None:
        """Generates hash of a file."""
        self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        hash = await self.manager.db_manager.hash_table.get_file_hash_exists(file, hash_type)
        try:
            if not hash:
                hash = await self.manager.hash_manager.hash_file(file, hash_type)
                await self.manager.db_manager.hash_table.insert_or_update_hash_db(
                    hash,
                    hash_type,
                    file,
                    original_filename,
                    referer,
                )
                self.manager.progress_manager.hash_progress.add_new_completed_hash()
            else:
                self.manager.progress_manager.hash_progress.add_prev_hash()
                await self.manager.db_manager.hash_table.insert_or_update_hash_db(
                    hash,
                    hash_type,
                    file,
                    original_filename,
                    referer,
                )
        except Exception as e:
            log(f"Error hashing '{file}' : {e}", 40, exc_info=True)
        else:
            return hash

    async def save_hash_data(self, media_item: MediaItem, hash: str | None) -> None:
        if not hash:
            return
        absolute_path = await asyncio.to_thread(media_item.complete_file.resolve)
        size = await asyncio.to_thread(get_size_or_none, media_item.complete_file)
        assert size
        self.hashed_media_items.add(media_item)
        if hash:
            media_item.hash = hash
        self.hashes_dict[hash][size].add(absolute_path)

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

    async def final_dupe_cleanup(self, final_dict: dict[str, dict]) -> None:
        """cleanup files based on dedupe setting"""
        to_trash = self.manager.config_manager.settings_data.dupe_cleanup_options.send_deleted_to_trash
        suffix = "Sent to trash " if to_trash else "Permanently deleted"

        async def delete_and_log(file: Path):
            try:
                deleted = await delete_file(file, to_trash)
                if deleted:
                    log(f"Removed new download '{file}' with hash {hash} [{suffix}]", 10)
                    self.manager.progress_manager.hash_progress.add_removed_file()

            except OSError as e:
                log(f"Unable to remove '{file}' with hash {hash}: {e}", 40)

        tasks = []
        get_matches = self.manager.db_manager.hash_table.get_files_with_hash_matches
        for hash, size_dict in final_dict.items():
            for size in size_dict:
                db_matches = await get_matches(hash, size, self.xxhash)
                for match in db_matches[1:]:
                    file = Path(*match[:2])
                    tasks.append(delete_and_log(file))

        await asyncio.gather(*tasks)

    async def get_file_hashes_dict(self) -> dict:
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
        coro = aiofiles.os.unlink(Path(path))

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
