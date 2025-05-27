from __future__ import annotations

import enum
from typing import Self

from cyberdrop_dl.types import MayBeUpperStrEnum, StrEnum


class Hashing(MayBeUpperStrEnum):
    OFF = enum.auto()
    IN_PLACE = enum.auto()
    POST_DOWNLOAD = enum.auto()


class HashAlgorithm(StrEnum):
    md5 = "md5"
    sha256 = "sha256"
    xxh128 = "xxh128"
    sha1 = "sha1"


class Hash(str):
    algorithm: HashAlgorithm
    value: str
    hash_string: str

    def __new__(cls, algorithm: HashAlgorithm, hash_value: str, /) -> Self:
        assert algorithm in HashAlgorithm, f"Invalid algorithm. Valid algorithms: {HashAlgorithm.values()}"
        assert hash_value
        self = super().__new__(cls, hash_value)
        self.algorithm = algorithm
        self.value = hash_value
        self.hash_string = f"{self.algorithm}:{self.value}"
        return self

    @staticmethod
    def from_hash_string(hash_string: str, /) -> Hash:
        assert ":" in hash_string, "input should be in the format 'algorithm:hash_value'"
        algo, _, hash_value = hash_string.partition(":")
        return Hash(HashAlgorithm(algo), hash_value)
