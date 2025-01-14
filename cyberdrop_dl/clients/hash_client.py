from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from send2trash import send2trash

from cyberdrop_dl.ui.prompts.basic_prompts import enter_to_continue
from cyberdrop_dl.utils.data_enums_classes.hash import Hashing
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


@asynccontextmanager
async def hash_scan_directory_context(manager: Manager) -> AsyncGenerator:
    await manager.async_db_hash_startup()
    yield
    await manager.close()


def hash_directory_scanner(manager: Manager, path: Path) -> None:
    asyncio.run(_hash_directory_scanner_helper(manager, path))
    enter_to_continue()


async def _hash_directory_scanner_helper(manager: Manager, path: Path):
    start_time = time.perf_counter()
    async with hash_scan_directory_context(manager):
        await manager.hash_manager.hash_client.hash_directory(path)
        manager.progress_manager.print_stats(start_time)


class HashClient:
    """Manage hashes and db insertion."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.hashes = defaultdict(lambda: None)
        self.xxhash = "xxh128"
        self.md5 = "md5"
        self.sha256 = "sha256"
        self.hashed_media_items: set[MediaItem] = set()
        self.hashes_dict: defaultdict[defaultdict[set[Path]]] = defaultdict(lambda: defaultdict(set))

    async def startup(self) -> None:
        pass

    async def hash_directory(self, path: Path) -> None:
        path = Path(path)
        with self.manager.live_manager.get_hash_live(stop=True):
            if not path.is_dir():
                raise NotADirectoryError
            for file in path.rglob("*"):
                await self._hash_item_helper(file, None, None)

    @staticmethod
    def _get_key_from_file(file: Path | str):
        return str(Path(file).absolute())

    async def _hash_item_helper(self, file: Path | str, original_filename: str, referer: URL):
        hash = await self._hash_item(file, original_filename, referer, hash_type=self.xxhash)
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_md5_hash:
            await self._hash_item(file, original_filename, referer, hash_type=self.md5)
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_sha256_hash:
            await self._hash_item(file, original_filename, referer, hash_type=self.sha256)
        return hash

    async def _hash_item(self, file: Path | str, original_filename: str, referer: URL, hash_type=None) -> str:
        """Generates hash of a file."""
        key = self._get_key_from_file(file)
        file = Path(file)
        if not file.is_file():
            return
        elif file.stat().st_size == 0:
            return
        elif file.suffix == ".part":
            return
        if self.hashes[(key, hash_type)]:
            return self.hashes[(key, hash_type)]
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
            log(f"Error hashing {file} : {e}", 40, exc_info=True)
        self.hashes[(key, hash_type)] = hash
        return hash

    async def hash_item(self, media_item: MediaItem) -> None:
        absolute_path = media_item.complete_file.resolve()
        size = media_item.complete_file.stat().st_size
        hash = await self._hash_item_helper(media_item.complete_file, media_item.original_filename, media_item.referer)

        self.hashed_media_items.add(media_item)
        self.hashes_dict[hash][size].add(absolute_path)

    async def hash_item_during_download(self, media_item: MediaItem) -> None:
        if self.manager.config_manager.settings_data.dupe_cleanup_options.hashing != Hashing.IN_PLACE:
            return
        try:
            await self.hash_item(media_item)
        except Exception as e:
            log(f"After hash processing failed: {media_item.complete_file} with error {e}", 40, exc_info=True)

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
        for hash, size_dict in final_dict.items():
            for size in size_dict:
                # Get all matches from the database
                db_matches = await self.manager.db_manager.hash_table.get_files_with_hash_matches(
                    hash, size, self.xxhash
                )
                all_matches = [Path(*match[:2]) for match in db_matches]
                for file in all_matches[1:]:
                    if not file.is_file():
                        continue
                    try:
                        self.delete_file(file)
                        log(f"Removed new download: {file} with hash {hash}", 10)
                        self.manager.progress_manager.hash_progress.add_removed_file()
                    except OSError as e:
                        log(f"Unable to remove {file = } with hash {hash} : {e}", 40)

    async def get_file_hashes_dict(self) -> dict:
        # first compare downloads to each other
        # get representive for each hash
        downloads = self.manager.path_manager.completed_downloads - self.hashed_media_items
        for media_item in downloads:
            if not media_item.complete_file.is_file():
                return
            try:
                self.hash_item(media_item)
            except Exception as e:
                msg = f"Unable to hash file = {media_item.complete_file.resolve()}: {e}"
                log(msg, 40)
        return self.hashes_dict

    def delete_file(self, path: Path) -> None:
        if self.manager.config_manager.settings_data.dupe_cleanup_options.send_deleted_to_trash:
            send2trash(path)
            log(f"sent file at{path} to trash", 10)
            return

        Path(path).unlink(missing_ok=True)
        log(f"permanently deleted file at {path}", 10)
