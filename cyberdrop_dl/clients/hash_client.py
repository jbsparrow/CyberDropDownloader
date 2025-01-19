from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from send2trash import send2trash

from cyberdrop_dl.utils.data_enums_classes.hash import Hashing
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem
import random
import string
import tempfile
import timeit

# def hash_directory_scanner(manager: Manager, path: Path) -> None:
#     asyncio.run(_hash_directory_scanner_helper(manager, path))
#     enter_to_continue()


def generate_random_values():
    """
    Generates random values for the given function:
        manager.db_manager.hash_table.queue_hash_db(hash_value, "xxhash", file, original_filename, referer)

    Returns:
        A tuple containing the generated random values:
        (hash_value, file, original_filename, referer)
    """

    # Generate random hash_value (example: hexadecimal string)
    hash_value = "".join(random.choices(string.hexdigits, k=32))

    # Generate random file path (example: using random words)
    with tempfile.NamedTemporaryFile(delete=False) as _:
        file = Path(_.name)
    # Generate random original_filename (similar to file)
    original_filename = "test"

    # Generate random referer URL (example: simplified URL)
    referers = ["google.com", "example.com", "wikipedia.org", "youtube.com"]
    referer = f"https://{random.choice(referers)}/"

    return hash_value, file, original_filename, referer


async def batch_helper(manager, num):
    await manager.async_db_hash_startup()
    for _ in range(num):
        hash_value, file, original_filename, referer = generate_random_values()
        await manager.db_manager.hash_table.queue_hash_db(hash_value, "xxhash", file, original_filename, referer)
        os.remove(file)
    await manager.db_manager.hash_table.batch_insert_or_update_hash_db()
    await manager.async_db_close()


async def iterative_helper(manager, num):
    await manager.async_db_hash_startup()
    for _ in range(num):
        hash_value, file, original_filename, referer = generate_random_values()
        await manager.db_manager.hash_table.insert_or_update_hash_db(
            hash_value, "xxhash", file, original_filename, referer
        )
        os.remove(file)
    await manager.async_db_close()


def hash_directory_scanner(manager: Manager, path: Path, number: int = 10):
    """
    Times the execution of the hash_directory_scanner function using timeit.

    Args:
        manager: The manager object.
        path: The path to the directory to hash.
        number: The number of times to run the function (default: 10).
    """

    def wrapper(num):
        asyncio.run(batch_helper(manager, num))

    def wrapper2(num):
        asyncio.run(iterative_helper(manager, num))

    for num in [100, 300, 500, 1000, 5000]:
        result = timeit.timeit(partial(wrapper2, num), number=number)
        print(f"Average execution time for iterative hash_directory_scanner @{num}: {result / number:.4f} seconds")
        result = timeit.timeit(partial(wrapper, num), number=number)
        print(f"Average execution time for batch hash_directory_scanner@ {num}: {result / number:.4f} seconds")
        pass
    pass


async def _hash_directory_scanner_helper(manager: Manager, path: Path):
    start_time = time.perf_counter()
    await manager.async_db_hash_startup()
    await manager.hash_manager.hash_client.hash_directory(path)
    manager.progress_manager.print_stats(start_time)
    await manager.async_db_close()


class HashClient:
    """Manage hashes and db insertion."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.xxhash = "xxh128"
        self.md5 = "md5"
        self.sha256 = "sha256"
        self.hashed_media_items: set[MediaItem] = set()
        self.hashes_dict: defaultdict[defaultdict[set[Path]]] = defaultdict(lambda: defaultdict(set))

    async def startup(self) -> None:
        pass

    async def hash_directory(self, path: Path) -> None:
        path = Path(path)
        # log(f"scanning {path} recursely to create hashes", 10)
        with self.manager.live_manager.get_hash_live(stop=True):
            if not path.is_dir():
                raise NotADirectoryError
            for file in path.rglob("*"):
                await self._hash_item_helper(file, None, None)
                # log(f"generated hashed for {file}", 10)
        await self.manager.db_manager.hash_table.batch_insert_or_update_hash_db()
        # log("inserted/updated database")

    @staticmethod
    def _get_key_from_file(file: Path | str):
        return str(Path(file).absolute())

    async def _hash_item_helper(self, file: Path | str, original_filename: str, referer: URL):
        file = Path(file)
        if not file.is_file():
            return
        elif file.stat().st_size == 0:
            return
        elif file.suffix == ".part":
            return
        hash = await self._get_item_hash(file, original_filename, referer, hash_type=self.xxhash)
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_md5_hash:
            await self._get_item_hash(file, original_filename, referer, hash_type=self.md5)
        if self.manager.config_manager.settings_data.dupe_cleanup_options.add_sha256_hash:
            await self._get_item_hash(file, original_filename, referer, hash_type=self.sha256)
        return hash

    async def _get_item_hash(self, file: Path | str, original_filename: str, referer: URL, hash_type) -> str:
        """Generates hash of a file."""
        self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        hash = await self.manager.db_manager.hash_table.get_file_hash_exists(file, hash_type)
        try:
            if not hash:
                hash = await self.manager.hash_manager.hash_file(file, hash_type)
                self.manager.progress_manager.hash_progress.add_new_completed_hash()
            else:
                self.manager.progress_manager.hash_progress.add_prev_hash()
            await self.manager.db_manager.hash_table.queue_or_insert_hash_db(
                hash, hash_type, file, original_filename, referer
            )
            return hash

        except Exception as e:
            log(f"Error hashing {file} : {e}", 40, exc_info=True)
        return hash

    def save_hash_data(self, media_item, hash):
        absolute_path = media_item.complete_file.resolve()
        size = media_item.complete_file.stat().st_size
        self.hashed_media_items.add(media_item)
        self.hashes_dict[hash][size].add(absolute_path)

    async def hash_item(self, media_item: MediaItem) -> None:
        hash = await self._hash_item_helper(media_item.complete_file, media_item.original_filename, media_item.referer)
        self.save_hash_data(media_item, hash)

    async def hash_item_during_download(self, media_item: MediaItem) -> None:
        if self.manager.config_manager.settings_data.dupe_cleanup_options.hashing != Hashing.IN_PLACE:
            return
        try:
            hash = await self._hash_item_helper(
                media_item.complete_file, media_item.original_filename, media_item.referer
            )
            self.save_hash_data(media_item, hash)
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
                await self.hash_item(media_item)
            except Exception as e:
                msg = f"Unable to hash file = {media_item.complete_file.resolve()}: {e}"
                log(msg, 40)
        # insert any hashes or data that has been saved to be batched
        await self.manager.db_manager.hash_table.batch_insert_or_update_hash_db()
        return self.hashes_dict

    def delete_file(self, path: Path) -> None:
        if self.manager.config_manager.settings_data.dupe_cleanup_options.send_deleted_to_trash:
            send2trash(path)
            log(f"sent file at{path} to trash", 10)
            return

        Path(path).unlink(missing_ok=True)
        log(f"permanently deleted file at {path}", 10)
