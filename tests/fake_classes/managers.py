from typing import Literal

from cyberdrop_dl.managers.cache_manager import CacheManager


class FakeCacheManager(CacheManager):
    def get(self, _: str) -> Literal[True]:
        return True

    def save(self, *_) -> None:
        return
