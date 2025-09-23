from __future__ import annotations

from dataclasses import Field, field
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp_client_cache import CacheBackend, SQLiteBackend

from cyberdrop_dl import __version__ as current_version
from cyberdrop_dl.scraper.filters import cache_filter_fn
from cyberdrop_dl.utils import yaml

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


class CacheManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

        self.request_cache: SQLiteBackend | CacheBackend = field(init=False)
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

    def load_request_cache(self) -> None:
        from cyberdrop_dl.supported_domains import SUPPORTED_FORUMS, SUPPORTED_WEBSITES

        rate_limiting_options = self.manager.config_manager.global_settings_data.rate_limiting_options
        urls_expire_after = {
            "*.simpcity.su": rate_limiting_options.file_host_cache_expire_after,
        }
        for host in SUPPORTED_WEBSITES.values():
            match_host = f"*.{host}" if "." in host else f"*.{host}.*"
            urls_expire_after[match_host] = rate_limiting_options.file_host_cache_expire_after
        for forum in SUPPORTED_FORUMS.values():
            urls_expire_after[forum] = rate_limiting_options.forum_cache_expire_after
        self.request_cache = SQLiteBackend(
            cache_name=self.manager.path_manager.cache_db,  # type: ignore
            autoclose=False,
            allowed_codes=(
                HTTPStatus.OK,
                HTTPStatus.NOT_FOUND,
                HTTPStatus.GONE,
                HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS,
            ),
            allowed_methods=["GET"],
            expire_after=timedelta(days=7),
            urls_expire_after=urls_expire_after,
            filter_fn=cache_filter_fn,
        )

    def get(self, key: str) -> Any:
        """Returns the value of a key in the cache."""
        return self._cache.get(key, None)

    def save(self, key: str, value: Any) -> None:
        """Saves a key and value to the cache."""
        self._cache[key] = value
        yaml.save(self.cache_file, self._cache)

    def dump(self, data: dict) -> None:
        """dumps the dictionary into the cache"""
        self._cache = data
        yaml.save(self.cache_file, self._cache)

    def remove(self, key: str) -> None:
        """Removes a key from the cache."""
        if key in self._cache:
            del self._cache[key]
            yaml.save(self.cache_file, self._cache)

    async def close(self):
        if not isinstance(self.request_cache, Field):
            try:
                await self.request_cache.close()
            except Exception:
                pass
        self.save("version", current_version)
