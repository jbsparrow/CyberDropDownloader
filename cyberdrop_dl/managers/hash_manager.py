from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from cyberdrop_dl.clients.hash_client import HashClient

try:
    from xxhash import xxh128 as xxhasher
except ImportError:
    xxhasher = None
from hashlib import md5 as md5hasher
from hashlib import sha256 as sha256hasher

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class HashManager:
    def __init__(self, manager: Manager) -> None:
        self.xx_hasher = xxhasher
        self.md5_hasher = md5hasher
        self.sha_256_hasher = sha256hasher
        self.hash_client = HashClient(manager)  # Initialize hash client in constructor
        self.manager = manager

    async def startup(self) -> None:
        await self.hash_client.startup()

    async def hash_file(self, filename: Path | str, hash_type: str) -> str:
        file_path = Path.cwd() / filename
        async with aiofiles.open(file_path, "rb") as fp:
            CHUNK_SIZE = 1024 * 1024  # 1MB
            filedata = await fp.read(CHUNK_SIZE)
            current_hasher = self._get_hasher(hash_type)  # Use the initialized hasher
            while filedata:
                current_hasher.update(filedata)
                filedata = await fp.read(CHUNK_SIZE)
            return current_hasher.hexdigest()

    def _get_hasher(self, hash_type: str):
        if hash_type == "xx128" and not self.xx_hasher:
            raise ImportError("xxhash module is not installed")
        assert self.xx_hasher
        if hash_type == "xxh128":
            return self.xx_hasher()
        elif hash_type == "md5":
            return self.md5_hasher()
        elif hash_type == "sha256":
            return self.sha_256_hasher()
        else:
            raise ValueError("Invalid hash type")
