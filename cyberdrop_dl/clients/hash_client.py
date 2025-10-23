from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from send2trash import send2trash

from cyberdrop_dl.data_structures.hash import Hashing
from cyberdrop_dl.ui.prompts.basic_prompts import enter_to_continue
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import get_size_or_none

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.config.config_model import DupeCleanup
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
        self._sem = asyncio.BoundedSemaphore(20)

    @property
    def _to_trash(self) -> bool:
        return self.dupe_cleanup_options.send_deleted_to_trash

    @property
    def _deleted_file_suffix(self) -> Literal["Sent to trash", "Permanently deleted"]:
        return "Sent to trash" if self._to_trash else "Permanently deleted"

    @property
    def dupe_cleanup_options(self) -> DupeCleanup:
        return self.manager.config.dupe_cleanup_options

    async def startup(self) -> None:
        pass

    async def hash_directory(self, path: Path) -> None:
        path = Path(path)
        with (
            self.manager.live_manager.get_hash_live(stop=True),
            self.manager.progress_manager.hash_progress.currently_hashing_dir(path),
        ):
            if not await asyncio.to_thread(path.is_dir):
                raise NotADirectoryError
            for file in path.rglob("*"):
                _ = await self.update_db_and_retrive_hash(file)

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
        if file.suffix in (".cdl_hls", ".cdl_hsl", ".part"):
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
                self.manager.progress_manager.hash_progress.add_new_completed_hash(hash_type)
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

        get_matches = self.manager.db_manager.hash_table.get_files_with_hash_matches
        async with asyncio.TaskGroup() as tg:

            async def delete_dupes(hash_value: str, size: int) -> None:
                db_matches = await get_matches(hash_value, size, "xxh128")
                for row in db_matches[1:]:
                    file = Path(row["folder"], row["download_filename"])
                    await self._sem.acquire()
                    tg.create_task(self._delete_and_log(file, hash_value))

            for hash_value, size_dict in final_dict.items():
                for size in size_dict:
                    tg.create_task(delete_dupes(hash_value, size))

    async def _delete_and_log(self, file: Path, xxh128_value: str) -> None:
        hash_string = f"xxh128:{xxh128_value}"
        try:
            deleted = await _delete_file(file, self._to_trash)
        except OSError as e:
            log(f"Unable to remove '{file}' ({hash_string}): {e}", 40)
        else:
            if not deleted:
                return

            msg = (
                f"Removed new download '{file}' [{self._deleted_file_suffix}]. "
                f"File hash matches with a previous download ({hash_string})"
            )
            log(msg, 10)
            self.manager.progress_manager.hash_progress.add_removed_file()

        finally:
            self._sem.release()

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


async def _delete_file(path: Path, to_trash: bool = True) -> bool:
    """Deletes a file and return `True` on success, `False` is the file was not found.

    Any other exception is propagated"""

    if to_trash:
        coro = asyncio.to_thread(send2trash, path)
    else:
        coro = asyncio.to_thread(path.unlink)

    try:
        await coro
        return True
    except FileNotFoundError:
        pass
    except OSError as e:
        # send2trash raises everything as a bare OSError. We should only ignore FileNotFound and raise everything else
        msg = str(e)
        if "File not found" not in msg:
            raise

    return False
