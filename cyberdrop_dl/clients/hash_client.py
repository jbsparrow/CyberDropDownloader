from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from send2trash import send2trash

from cyberdrop_dl.ui.prompts.continue_prompt import enter_to_continue
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem


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
        self.prev_hashes = None
        self.xxhash="xxh128"
        self.md5="md5"
        self.sha256="sha256"

    async def startup(self) -> None:
        self.prev_hashes = set(await self.manager.db_manager.hash_table.get_all_unique_hashes(self.xxhash))

    async def hash_directory(self, path: Path) -> None:
        path = Path(path)
        async with self.manager.live_manager.get_hash_live(stop=True):
            if not path.is_dir():
                raise NotADirectoryError
            for file in path.rglob("*"):
                await self.hash_item_helper(file, None, None)

    @staticmethod
    def _get_key_from_file(file: Path | str):
        return str(Path(file).absolute())
    async def hash_item_helper(self, file: Path | str, original_filename: str, referer: URL):
        hash=await self.hash_item(file, original_filename,referer,hash_type=self.xxhash)
        if self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["Hashing_Modications"]["allow_md5_hash"]:
            await self.hash_item(file, original_filename,referer,hash_type=self.md5)
        if self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["Hashing_Modications"]["allow_sha256_hash"]:
            await self.hash_item(file, original_filename, referer, hash_type=self.sha256)
        return hash


    async def hash_item(self, file: Path | str, original_filename: str, referer: URL,hash_type=None) -> str:
        """Generates hash of a file."""
        key = self._get_key_from_file(file)
        file = Path(file)
        if not file.is_file():
            return None
        if self.hashes[(key,hash_type)]:
            return self.hashes[(key,hash_type)]
        self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        hash = await self.manager.db_manager.hash_table.get_file_hash_exists(file,hash_type)
        try:
            if not hash:
                hash = await self.manager.hash_manager.hash_file(file,hash_type)
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
        self.hashes[(key,hash_type)] = hash
        return hash

    async def hash_item_during_download(self, media_item: MediaItem) -> None:
        try:
                
            if not self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["enable_dedupe_settings"]:
                return
            if self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["Hashing_Modications"]["hash_after_all_downloads"]:
                return
            await self.hash_item_helper(media_item.complete_file, media_item.original_filename, media_item.referer)
        except Exception as e:
            log(f"After hash processing failed: {media_item.complete_file} with error {e}", 40, exc_info=True)

    async def cleanup_dupes(self) -> None:
        with self.manager.live_manager.get_hash_live(stop=True):
            if not self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["enable_dedupe_settings"]:
                return
            file_hashes_dict = await self.get_file_hashes_dict()
        with self.manager.live_manager.get_remove_file_via_hash_live(stop=True):
            final_candiates_dict = self.get_candiate_per_group(file_hashes_dict)
            await self.final_dupe_cleanup(final_candiates_dict)

    async def final_dupe_cleanup(self, final_dict: dict[str, dict]) -> None:
        for hash, size_dict in final_dict.items():
            for size, data in size_dict.items():
                selected_file = Path(data["selected"])
                other_files = data["others"]
                # Get all matches from the database
                all_matches = [
                    Path(x[0], x[1])
                    for x in await self.manager.db_manager.hash_table.get_files_with_hash_matches(hash, size,self.xxhash)
                ]
                # Filter out files with the same path as any file in other_files
                other_matches = [match for match in all_matches if str(match) not in other_files]
                # Filter files based  on if the file exists
                existing_other_matches = [file for file in other_matches if file.exists()]

                if self.delete_all_prev_downloads():
                    for ele in existing_other_matches:
                        if not ele.exists():
                            continue
                        try:
                            if self.send2trash(ele):
                                log(f"removed prev download: {ele!s} with hash {hash}", 10)
                                self.manager.progress_manager.hash_progress.add_removed_prev_file()
                        except OSError:
                            continue
                # keep a previous downloads
                else:
                    for ele in existing_other_matches[1:]:
                        if not ele.exists():
                            continue
                        try:
                            if self.send2trash(ele):
                                log(f"removed prev download: {ele!s} with hash {hash}", 10)
                                self.manager.progress_manager.hash_progress.add_removed_prev_file()
                        except OSError:
                            continue
                # delete selected current download
                if self.delete_selected_current_download(hash, selected_file):
                    try:
                        if selected_file.exists():
                            if self.send2trash(selected_file):
                                log(f"removed new download:{selected_file} with hash {hash}", 10)
                            self.manager.progress_manager.hash_progress.add_removed_file()

                    except OSError:
                        pass

    async def get_file_hashes_dict(self) -> dict:
        hashes_dict = defaultdict(lambda: defaultdict(list))
        # first compare downloads to each other
        for media_item in list(self.manager.path_manager.completed_downloads):
            hash = await self.hash_item_helper(media_item.complete_file, media_item.original_filename, media_item.referer)
            item = media_item.complete_file.absolute()
            try:
                size = item.stat().st_size
                if hash:
                    hashes_dict[hash][size].append(item)
            except Exception as e:
                log(f"After hash processing failed: {item} with error {e}", 40, exc_info=True)
        return hashes_dict

    def get_candiate_per_group(self, hashes_dict: dict[str, dict[int, list[Path]]]) -> dict:
        # create dictionary with one selected file, per value and list of other files with matching hashes
        for hash, size_dict in hashes_dict.items():
            for size, files in size_dict.items():
                selected_file = None
                for file in files:
                    if file.is_file():
                        selected_file = file
                        if file in self.manager.path_manager.prev_downloads_paths:
                            break
                        continue

                for file in filter(lambda x: x != selected_file, files):
                    try:
                        if self.send2trash(file):
                            log(f"removed new download : {file} with hash {hash}", 10)
                            self.manager.progress_manager.hash_progress.add_removed_file()
                    except OSError:
                        pass
                if selected_file:
                    size_dict[size] = {
                        "selected": selected_file,
                        "others": [str(x.absolute()) for x in files],
                    }
                else:
                    del size_dict[size]
        return hashes_dict

    def send2trash(self, path: Path) -> None:
        if self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["Deletion_Settings"]["disable_all_file_deletions"]:
            return False
        elif not self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["Deletion_Settings"]["send_deleted_to_trash"]:
            Path(path).unlink(missing_ok=True)
            log(f"permanently deleted file at {path}", 10)
            return True
        else:
            send2trash(path)
            log(f"sent file at{path} to trash", 10)
            return True

    def delete_all_prev_downloads(self) -> bool:
        return not self.keep_prev_file()
    
    
    def delete_selected_current_download(self, hash: str, selected_file: Path | str) -> bool:
        return not self.keep_selected_current_download(hash, selected_file) 
   
    def keep_selected_current_download(self, hash: str, selected_file: Path | str) -> bool:
        return bool(
            self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["Deletion_Settings"]["keep_new_download"]
            or hash not in self.prev_hashes
            or Path(selected_file) in self.manager.path_manager.prev_downloads_paths,
        )
    
    def keep_prev_file(self) -> bool:
        return self.manager.config_manager.settings_data["Dupe_Cleanup_Options"]["Deletion_Settings"]["keep_prev_download"]
    

