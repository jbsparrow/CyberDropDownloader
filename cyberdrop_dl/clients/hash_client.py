import  pathlib

from contextlib import asynccontextmanager
from collections import defaultdict
import asyncio
from cyberdrop_dl.utils.utilities import log




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
        # #remove downloaded files, so each group only has the first downloaded file
        final_list=[]
        with self.manager.live_manager.get_hash_remove_live() :
            for hash,size_dict in hashes_dict.items():
                for size_group in size_dict.values():
                    for ele in size_group:
                        match=False
                        if match:
                            await self.manager.progress_manager.hash_progress.add_removed_file()
                            ele.unlink(missing_ok=True)
                        elif ele.exists():
                            match=ele
                            final_list.append((hash,ele))


            # compare hashes against all hashes in db
            for ele in final_list:
                current_hash=ele[0]
                current_file=ele[1]
                size=current_file.stat().st_size
                # get all files with same hash
                all_matches=list(map(lambda x:pathlib.Path(x[0],x[1]),await self.manager.db_manager.hash_table.get_files_with_hash_matches(current_hash,size)))
                #what to count as a previous match
                prev_matches = list(filter(lambda x: x != current_file and (x.exists() if not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['count_missing_as_existing'] else True ), all_matches))

               
                #what do do with prev matches and current file
                if len(prev_matches)==0:
                    continue
                elif self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['keep_prev_download']:
                    current_file.unlink(missing_ok=True)
                else:
                    for ele in prev_matches:
                        ele.unlink(missing_ok=True)
        
    
