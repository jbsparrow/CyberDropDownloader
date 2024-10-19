import os  # Import os for file path manipulation

<<<<<<< HEAD
class Hasher:
    def __init__(self):
        pass
    
    def hash_file(self,filename):
        file_hash = self.hasher()
        with open(filename,"rb") as fp:
              CHUNK_SIZE = 1024 * 1024  # 1 mb
              filedata = fp.read(CHUNK_SIZE)
              while filedata:
                    file_hash.update(filedata)
                    filedata = fp.read(CHUNK_SIZE)
              return file_hash.hexdigest()
    @property
    def hasher(self):
      try:
          import xxhash
          return xxhash.xxh128
      except ImportError:
          import hashlib
          return hashlib.md5
=======
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
>>>>>>> 839f98a54acb029a0090d269d5253929a5b0f38b
