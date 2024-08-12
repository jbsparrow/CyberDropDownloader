import  pathlib

from contextlib import asynccontextmanager
from collections import defaultdict
import asyncio
from cyberdrop_dl.utils.utilities import log
from send2trash import send2trash
from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem




class HashClient:
    """Manage hashes and db insertion"""
    def __init__(self,manager):
        self.manager=manager
        
    @asynccontextmanager
    async def _manager_context(self):
        await self.manager.async_db_hash_startup()
        yield
        await self.manager.close()
    
    def hash_directory(self,path):
        asyncio.run(self._hash_directory_helper(path))

    async def _hash_directory_helper(self,path):
        async with self._manager_context():
            with self.manager.live_manager.get_hash_live(stop=True):
                #force start live  manager for db connection
                self.manager.startup()
                if not pathlib.Path(path).is_dir():
                    raise Exception("Path is not a directory")
                for file in pathlib.Path(path).glob("**/*"):
                    await self.hash_item(file)
                
    async def hash_item(self,file):
        if not file.is_file():
            return
        await self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        hash=await self.manager.db_manager.hash_table.get_file_hash_exists(file)
        if not hash:
            try:
                hash = await self.manager.hash_manager.hash_file(file)
                await self.manager.db_manager.hash_table.insert_or_update_hash_db(hash, file.stat().st_size, file)
                await self.manager.progress_manager.hash_progress.add_completed_hash()
            except Exception as e:
                await log(f"Error hashing {file} : {e}",40)


        else:
            await self.manager.progress_manager.hash_progress.add_prev_hash()
        return  hash

    
    async def hash_item_during_download(self,media_item:MediaItem):
        try:
            if self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['hash_while_downloading']:
                    self.hash_item(media_item.complete_file)
        except Exception as e:
            await log(f"After media processing failed: {media_item.complete_file} with error {e}", 40)


    async def cleanup_dupes(self):
        with self.manager.live_manager.get_hash_live() :
            if not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['delete_after_download']:
                return
            hashes_dict=defaultdict(lambda: defaultdict(list))
            # first compare downloads to each other
            for item in self.manager.path_manager.completed_downloads:
                hash=await self.hash_item(item)
                size=item.stat().st_size
                if hash:
                    hashes_dict[hash][size].append(item)
        with self.manager.live_manager.get_remove_file_via_hash_live() :
            # #remove downloaded files, so each group only has the first downloaded file
            for size_dict in hashes_dict.values():
                for size, files in size_dict.items():
                    selected_file = None
                    for file in files:
                        if file.is_file():
                            selected_file = file
                            break 
                    for file in filter(lambda x:x!=selected_file,files):
                        try:
                            send2trash(file)
                            await self.manager.progress_manager.hash_progress.add_removed_file()
                        except OSError:
                            pass

                    if selected_file:
                        size_dict[size] = {'selected': selected_file, 'others': list(map(lambda x:str(x.absolute()),files))}
                    else:
                        del size_dict[size]           
            
            for hash, size_dict in hashes_dict.items():
                for size, data in size_dict.items():
                    selected_file = data['selected']
                    other_files = data['others']

                    # Get all matches from the database
                    all_matches = list(map(lambda x: pathlib.Path(x[0], x[1]),
                    await self.manager.db_manager.hash_table.get_files_with_hash_matches(hash, size)))

                    # Filter out files with the same path as any file in other_files
                    filtered_matches = [match for match in all_matches if match not in other_files]
                    #Filter files based  on if the file exists
                    filtered_matches = list(filter(lambda x: x.exists() if not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['count_missing_as_existing'] else True ), all_matches)

                    #what do do with prev matches and current file
                    if len(filtered_matches)==0:
                        continue
                    elif self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['keep_prev_download']:
                        try:
                            send2trash(selected_file)
                        except OSError:
                            pass
                        await self.manager.progress_manager.hash_progress.add_removed_file()
                    else:
                        for ele in filtered_matches:
                            try:
                                send2trash(ele)
                            except OSError:
                                pass
                            await self.manager.progress_manager.hash_progress.add_removed_prev_file()
            
        
