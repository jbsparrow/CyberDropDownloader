from __future__ import annotations

from dataclasses import field
from typing import TYPE_CHECKING, Any

from cyberdrop_dl.utils import yaml

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


class CacheManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

        self.cache_file: Path = field(init=False)
        self._cache = {}

    def startup(self, cache_file: Path) -> None:
        """Ensures that the cache file exists."""
        self.cache_file = cache_file
        if not self.cache_file.is_file():
            self.save("default_config", "Default")

        self.load()
        if self.manager.parsed_args.cli_only_args.appdata_folder:
            self.save("first_startup_completed", True)

    def load(self) -> None:
        """Loads the cache file into memory."""
        self._cache = yaml.load(self.cache_file)

    def get(self, key: str) -> Any:
        """Returns the value of a key in the cache."""
        return self._cache.get(key, None)

    def save(self, key: str, value: Any) -> None:
        """Saves a key and value to the cache."""
        self._cache[key] = value
        yaml.save(self.cache_file, self._cache)

    def remove(self, key: str) -> None:
        """Removes a key from the cache."""
        if key in self._cache:
            del self._cache[key]
            yaml.save(self.cache_file, self._cache)
