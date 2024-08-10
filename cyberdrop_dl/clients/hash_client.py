import  pathlib
from contextlib import asynccontextmanager
from cyberdrop_dl.managers.db_manager import DBManager
import asyncio


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
        asyncio.run(self.hash_directory_helper(path))

    async def hash_directory_helper(self,path):
        async with self._manager_context():
            if not pathlib.Path(path).is_dir():
                raise Exception("Path is not a directory")
            for file in pathlib.Path(path).glob("**/*"):
                if await self.manager.db_manager.hash_table.check_file_hash_exists(file):
                    continue
                else:
                    hash = await self.manager.hash_manager.hash_file(file)
                    await self.manager.db_manager.hash_table.insert_or_update_hash_db(hash, file.stat().st_size, file.name, file.parent)
            
