import asyncio
import pathlib
from collections import defaultdict
from contextlib import asynccontextmanager

from send2trash import send2trash

from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem
from cyberdrop_dl.utils.utilities import log
from cyberdrop_dl.ui.prompts.continue_prompt import enter_to_continue


@asynccontextmanager
async def hash_scan_directory_context(manager):
    await manager.async_db_hash_startup()
    yield
    await manager.close()


def hash_directory_scanner(manager, path):
    asyncio.run(_hash_directory_scanner_helper(manager, path))
    enter_to_continue()


async def _hash_directory_scanner_helper(manager, path):
    async with hash_scan_directory_context(manager):
        await manager.hash_manager.hash_client.hash_directory(path)
        await manager.progress_manager.print_stats()
       
        



class HashClient:
    """Manage hashes and db insertion"""

    def __init__(self, manager):
        self.manager = manager
        self.hashes = defaultdict(lambda: None)
        self.prev_hashes = None


    async def startup(self):
        self.prev_hashes = set(await self.manager.db_manager.hash_table.get_all_unique_hashes())

    async def hash_directory(self, path):
        async with self.manager.live_manager.get_hash_live(stop=True):
            if not pathlib.Path(path).is_dir():
                raise Exception("Path is not a directory")
            for file in pathlib.Path(path).glob("**/*"):
                await self.hash_item(file, None, None)

    def _get_key_from_file(self, file):
        return str(pathlib.Path(file).absolute())

    async def hash_item(self, file, original_filename, refer):
        key = self._get_key_from_file(file)
        file = pathlib.Path(file)
        if not file.is_file():
            return
        elif self.hashes[key]:
            return self.hashes[key]
        await self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        hash = await self.manager.db_manager.hash_table.get_file_hash_exists(file)
        try:
            if not hash:
                hash = await self.manager.hash_manager.hash_file(file)
                await self.manager.db_manager.hash_table.insert_or_update_hash_db(hash, file, original_filename, refer)
                await self.manager.progress_manager.hash_progress.add_new_completed_hash()
            else:
                await self.manager.progress_manager.hash_progress.add_prev_hash()
                await self.manager.db_manager.hash_table.insert_or_update_hash_db(hash
                , file, original_filename, refer)
        except Exception as e:
            await log(f"Error hashing {file} : {e}", 40)
        self.hashes[key] = hash
        return hash

    async def hash_item_during_download(self, media_item: MediaItem):
        try:
            if self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['hash_while_downloading']:
                await self.hash_item(media_item.complete_file, media_item.original_filename, media_item.referer
                                    )
        except Exception as e:
            await log(f"After hash processing failed: {media_item.complete_file} with error {e}", 40)

    async def cleanup_dupes(self):
        async with self.manager.live_manager.get_hash_live():
            if not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['delete_after_download']:
                return
            file_hashes_dict=await self.get_file_hashes_dict()
        async with self.manager.live_manager.get_remove_file_via_hash_live():
            final_candiates_dict=await self.get_candiate_per_group(file_hashes_dict)
            await self.final_dupe_cleanup(final_candiates_dict)

    async def final_dupe_cleanup(self,final_dict):
            for hash, size_dict in final_dict.items():
                for size, data in size_dict.items():
                    selected_file = pathlib.Path(data['selected'])
                    other_files = data['others']

                    # Get all matches from the database
                    all_matches = list(map(lambda x: pathlib.Path(x[0], x[1]),
                                           await self.manager.db_manager.hash_table.get_files_with_hash_matches(hash,
                                                                                                                size)))

                    # Filter out files with the same path as any file in other_files
                    other_matches = [match for match in all_matches if str(match) not in other_files]
                    # Filter files based  on if the file exists
                    existing_other_matches = list(filter(lambda x: x.exists(), other_matches))

                    #delete all prev files
                    if self.delete_all_prev_download() :
                        for ele in existing_other_matches:
                            if not ele.exists():
                                continue
                            try:
                                self.send2trash(ele)
                                await log(f"Sent prev download: {str(ele)} to trash with hash {hash}", 10)
                                await self.manager.progress_manager.hash_progress.add_removed_prev_file()
                            except OSError:
                                continue
                    # keep a previous downloads
                    else:
                        for ele in existing_other_matches[1:]:
                            if not ele.exists():
                                continue
                            try:
                                self.send2trash(ele)
                                await log(f"Sent prev download: {str(ele)} to trash with hash {hash}", 10)
                                await self.manager.progress_manager.hash_progress.add_removed_prev_file()
                            except OSError:
                                continue
                    # delete current download
                    if self.delete_current_download(hash,selected_file):
                        try:
                            if selected_file.exists():
                                self.send2trash(selected_file)
                                await log(f"Sent new download:{str(selected_file)} to trash with hash {hash}", 10)
                                await self.manager.progress_manager.hash_progress.add_removed_file()

                        except OSError:
                            pass
    async def get_file_hashes_dict(self):
            hashes_dict = defaultdict(lambda: defaultdict(list))
            # first compare downloads to each other
            for media_item in list(self.manager.path_manager.completed_downloads):
                hash = await self.hash_item(media_item.complete_file, media_item.original_filename, media_item.referer)
                item = media_item.complete_file.absolute()
                try:
                    size = item.stat().st_size
                    if hash:
                        hashes_dict[hash][size].append(item)
                except Exception as e:
                    await log(f"After hash processing failed: {item} with error {e}", 40)
            return hashes_dict
    
    async def get_candiate_per_group(self,hashes_dict):
            #remove downloaded files, so each group only has the one previously downloaded file or the first downloaded file
            for hash, size_dict in hashes_dict.items():
                for size, files in size_dict.items():
                    selected_file = None
                    for file in files:
                        if file.is_file() and file in self.manager.path_manager.prev_downloads_paths:
                            selected_file = file
                            break
                        elif file.is_file():
                            selected_file = file
                            continue
                    for file in filter(lambda x: x != selected_file, files):
                        try:
                            self.send2trash(file)
                            await log(f"Sent new download : {str(file)} to trash with hash {hash}", 10)
                            await self.manager.progress_manager.hash_progress.add_removed_file()
                        except OSError:
                            pass

                    if selected_file:
                        size_dict[size] = {'selected': selected_file,
                                           'others': list(map(lambda x: str(x.absolute()), files))}
                    else:
                        del size_dict[size]
            return hashes_dict

    def send2trash(self, path):
        if self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['delete_off_disk']:
            pathlib.Path(path).unlink(missing_ok=True)
        else:
            send2trash(path)

    def delete_all_prev_download(self):
        return not self.keep_prev_file()
    def delete_current_download(self,hash,selected_file):
        return not self.keep_new_download(hash,selected_file)
    def keep_new_download(self,hash,selected_file):
        if self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['keep_new_download']:
            return True
        elif hash not in self.prev_hashes:
            return True
        elif str(selected_file) in self.manager.path_manager.prev_downloads_paths:
            return True
    def keep_prev_file(self): 
        return (self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['keep_prev_download'])
