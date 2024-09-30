import os  # Import os for file path manipulation

import aiofiles

from cyberdrop_dl.clients.hash_client import HashClient


class HashManager:
    def __init__(self, manager):
        self.hasher = self._get_hasher()  # Initialize hasher in constructor
        self.hash_client = HashClient(manager)  # Initialize hash client in constructor

    async def startup(self):
        await self.hash_client.startup()

    def _get_hasher(self):
        """Tries to import xxhash, otherwise falls back to hashlib.md5"""
        try:
            import xxhash  # type: ignore
            return xxhash.xxh128
        except ImportError:
            import hashlib
            return hashlib.md5

    async def hash_file(self, filename):
        file_path = os.path.join(os.getcwd(), filename)  # Construct full file path
        async with aiofiles.open(file_path, "rb") as fp:
            CHUNK_SIZE = 1024 * 1024  # 1 mb
            filedata = await fp.read(CHUNK_SIZE)
            hasher = self.hasher()  # Use the initialized hasher
            while filedata:
                hasher.update(filedata)
                filedata = await fp.read(CHUNK_SIZE)
            return hasher.hexdigest()
