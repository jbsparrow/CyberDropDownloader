from cyberdrop_dl.managers.cache_manager import CacheManager


class FakeCacheManager(CacheManager):
    def get(self, _: str) -> True:
        return True

    def save(self, *_) -> None:
        return
