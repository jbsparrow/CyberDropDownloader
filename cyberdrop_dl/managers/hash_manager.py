from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from cyberdrop_dl.clients.hash_client import HashClient

try:
    from xxhash import xxh128 as hasher
except ImportError:
    from hashlib import md5 as hasher

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class HashManager:
    def __init__(self, manager: Manager) -> None:
        self.hasher = hasher
        self.hash_client = HashClient(manager)  # Initialize hash client in constructor

    async def startup(self) -> None:
        await self.hash_client.startup()

    async def hash_file(self, filename: str) -> str:
        file_path = Path.cwd() / filename
        async with aiofiles.open(file_path, "rb") as fp:
            CHUNK_SIZE = 1024 * 1024  # 1MB
            filedata = await fp.read(CHUNK_SIZE)
            current_hasher = hasher()  # Use the initialized hasher
            while filedata:
                current_hasher.update(filedata)
                filedata = await fp.read(CHUNK_SIZE)
            return current_hasher.hexdigest()
