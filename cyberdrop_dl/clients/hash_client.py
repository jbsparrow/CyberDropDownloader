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
        self.hashes=defaultdict(lambda:None)
        self.prev_hashes=set()
        
    @asynccontextmanager
    async def _manager_context(self):
        await self.manager.async_db_hash_startup()
        yield
        await self.manager.close()
    
    def hash_directory(self,path):
        asyncio.run(self._hash_directory_helper(path))

    async def _hash_directory_helper(self,path):
        async with self._manager_context():
            async with self.manager.live_manager.get_hash_live(stop=True):
                #force start live  manager for db connection
                self.manager.startup()
                if not pathlib.Path(path).is_dir():
                    raise Exception("Path is not a directory")
                for file in pathlib.Path(path).glob("**/*"):
                    await self.hash_item(file,None,None)
    def _get_key_from_file(self,file):
        return str(pathlib.Path(file).absolute())          
    async def hash_item(self,file,original_filename,refer):
        key=self._get_key_from_file(file)
        file=pathlib.Path(file)
        refer=str(refer)
        original_filename=str(original_filename)
        if not file.is_file():
            return
        elif self.hashes[key]:
            return self.hashes[key]
        await self.manager.progress_manager.hash_progress.update_currently_hashing(file)
        hash=await self.manager.db_manager.hash_table.get_file_hash_exists(file)
        try:
            if not hash:
                hash = await self.manager.hash_manager.hash_file(file)
                await self.manager.db_manager.hash_table.insert_or_update_hash_db(hash,file,original_filename,refer)
                await self.manager.progress_manager.hash_progress.add_new_completed_hash()
            else:
                await self.manager.progress_manager.hash_progress.add_prev_hash()
                await self.manager.db_manager.hash_table.insert_or_update_hash_db(hash,file,original_filename,refer)
                self.prev_hashes.add(key)
        except Exception as e:
                await log(f"Error hashing {file} : {e}",40)
        self.hashes[key]=hash
        return  hash

    
    async def hash_item_during_download(self,media_item:MediaItem):
        try:
            if self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['hash_while_downloading']:
                    await self.hash_item(media_item.complete_file,media_item.original_filename,media_item.referer
                                         )
        except Exception as e:
            await log(f"After hash processing failed: {media_item.complete_file} with error {e}", 40)


    async def cleanup_dupes(self):
        async with self.manager.live_manager.get_hash_live() :
            if not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['delete_after_download']:
                return
            hashes_dict=defaultdict(lambda: defaultdict(list))
            # first compare downloads to each other
            for media_item in list(self.manager.path_manager.completed_downloads):
                
                hash=await self.hash_item(media_item.complete_file,media_item.original_filename,media_item.referer)
                item=media_item.complete_file.absolute()
                try:
                    size=item.stat().st_size
                    if hash:
                        hashes_dict[hash][size].append(item)
                except Exception as e:
                    await log(f"After hash processing failed: {item} with error {e}", 40)

        async with self.manager.live_manager.get_remove_file_via_hash_live() :
            # #remove downloaded files, so each group only has the first downloaded file
            for hash,size_dict in hashes_dict.items():
                for size, files in size_dict.items():
                    selected_file = None
                    for file in files:
                        if file.is_file():
                            selected_file = file
                            break 
                    for file in filter(lambda x:x!=selected_file,files):
                        try:
                            send2trash(file)
                            await log(f"Sent new download : {str(file)} to trash with hash {hash}", 10)
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
                    filtered_matches = [match for match in all_matches if str(match) not in other_files]
                    #Filter files based  on if the file exists
                    filtered_matches = list(filter(lambda x: x.exists(),filtered_matches )) 
                    
                    #what do do with prev matches and current file
                    if len(filtered_matches) == 0:
                        pass
                    elif not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['keep_prev_download']:
                        for ele in filtered_matches:
                            if not ele.exists():
                                continue
                            try:
                                send2trash(ele)
                                await log(f"Sent prev download: {str(ele)} to trash with hash {hash}", 10)
                                await self.manager.progress_manager.hash_progress.add_removed_prev_file()
                            except OSError:
                                continue
                    #delete all prev match except for one
                    else:
                         for ele in filtered_matches[1:]:
                            if not ele.exists():
                                continue
                            try:
                                send2trash(ele)
                                await log(f"Sent prev download: {str(ele)} to trash with hash {hash}", 10)
                                await self.manager.progress_manager.hash_progress.add_removed_prev_file()
                            except OSError:
                                continue
            
                    if not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['keep_new_download'] and self._get_key_from_file(ele) in self.prev_hashes:
                        try:
                            if ele.exists():
                                send2trash(ele)
                                await log(f"Sent new download:{str(ele)} to trash with hash {hash}", 10)
                                await self.manager.progress_manager.hash_progress.add_removed_file()

                        except OSError:

                            pass
                    