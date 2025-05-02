from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import aiofiles
from typing_extensions import Buffer

from cyberdrop_dl.clients.hash_client import HashClient
from cyberdrop_dl.utils.constants import HashType

try:
    from xxhash import xxh128 as xxhasher
except ImportError:
    xxhasher = None
from hashlib import md5 as md5_hasher
from hashlib import sha256 as sha256_hasher

if TYPE_CHECKING:
    from collections.abc import Callable


class HASH(Protocol):
    def hexdigest(self) -> str: ...
    def update(self, obj: Buffer, /) -> None: ...


hashers: dict[str, Callable[..., HASH]] = {
    HashType.xxh128: xxhasher,  # type: ignore
    HashType.md5: md5_hasher,
    HashType.sha256: sha256_hasher,
}

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class HashManager:
    def __init__(self, manager: Manager) -> None:
        self.hash_client = HashClient(manager)  # Initialize hash client in constructor
        self.manager = manager

    async def startup(self) -> None:
        await self.hash_client.startup()

    async def hash_file(self, filename: Path, hash_type: HashType) -> str:
        file_path = Path.cwd() / filename
        async with aiofiles.open(file_path, "rb") as file_io:
            CHUNK_SIZE = 1024 * 1024  # 1MB
            filedata = await file_io.read(CHUNK_SIZE)
            current_hasher = self._get_hasher(hash_type)
            while filedata:
                current_hasher.update(filedata)
                filedata = await file_io.read(CHUNK_SIZE)
            return current_hasher.hexdigest()

    def _get_hasher(self, hash_type: HashType) -> HASH:
        if hash_type == HashType.xxh128 and not xxhasher:
            raise ImportError("xxhash module is not installed")
        return hashers[hash_type]()
