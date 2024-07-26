
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
              return file_hash.digest()
    @property
    def hasher(self):
      try:
          import xxhash
          return xxhash.xxh128
      except ImportError:
          import hashlib
          return hashlib.md5
