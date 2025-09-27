from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Protocol, cast

import aiofiles

from cyberdrop_dl.clients.hash_client import HashClient
from cyberdrop_dl.data_structures.hash import HashAlgo

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


try:
    from xxhash import xxh128 as xxhasher
except ImportError:
    xxhasher = cast("type[_Hasher]", lambda: ImportError("xxhash module is not installed"))


class _Hasher(Protocol):
    def update(self, input: bytes, /) -> None: ...
    def digest(self) -> bytes: ...
    def hexdigest(self) -> str: ...


_HASHERS: dict[HashAlgo, Callable[[], _Hasher]] = {
    HashAlgo.md5: hashlib.md5,
    HashAlgo.sha256: hashlib.sha256,
    HashAlgo.xxh128: xxhasher,
}

_CHUNK_SIZE = 1024 * 1024  # 1MB


class HashManager:
    def __init__(self, manager: Manager) -> None:
        self.hash_client = HashClient(manager)
        self.manager = manager

    async def compute_hash(self, file_path: Path, hash_type: HashAlgo) -> str:
        current_hasher = _HASHERS[hash_type]()
        async with aiofiles.open(file_path, "rb") as fp:
            while filedata := await fp.read(_CHUNK_SIZE):
                current_hasher.update(filedata)

        return current_hasher.hexdigest()
