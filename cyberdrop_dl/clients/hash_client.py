import  pathlib

from contextlib import asynccontextmanager
from collections import defaultdict
import asyncio
from rich.live import Live




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
            with self.manager.live_manager.get_hash_live():
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
            hash = await self.manager.hash_manager.hash_file(file)
            await self.manager.db_manager.hash_table.insert_or_update_hash_db(hash, file.stat().st_size, file)
            await self.manager.progress_manager.hash_progress.add_completed_hash()

        else:
            await self.manager.progress_manager.hash_progress.add_prev_hash()
        return  hash

    async def cleanup_dupes(self):
        with self.manager.live_manager.get_remove_hash_live() :
            if not self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['delete_after_download']:
                return
            hashes_dict=defaultdict(list)
            # first compare downloads to each other
            for item in self.manager.path_manager.completed_downloads:
                hash=await self.hash_item(item)
                if hash:
                    hashes_dict[hash].append(item)
            #remove downloaded files, so each group only has the first downloaded file
            final_list=[]
            for key,group in hashes_dict.items():
                #double check files exits
                match=False
                for ele in group:
                    if match:
                        ele.unlink(missing_ok=True)
                    elif ele.exists():
                        match=ele
                        final_list.append((key,ele))
            # compare hashes against all hashes in db
            for ele in final_list:
                hash=ele[0]
                path=ele[1]
                size=pathlib.Path(path).stat().st_size
                # get all files with same hash
                all_matches=list(map(lambda x:pathlib.Path(x[0],x[1]),await self.manager.db_manager.hash_table.get_files_with_hash_matches(hash,size)))
                # delete files if more then one match exists
                matches=list(filter(lambda x:x!=path and x.exists(),all_matches))
                if len(matches)==0:
                    continue
                elif self.manager.config_manager.global_settings_data['Dupe_Cleanup_Options']['keep_current_download']:
                    for ele in matches:
                        ele.unlink(missing_ok=True)
                else:
                    path.unlink(missing_ok=True)
                    for ele in matches:
                        ele.unlink(missing_ok=True)
            
            
