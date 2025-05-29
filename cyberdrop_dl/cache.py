from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp_client_cache import SQLiteBackend

from cyberdrop_dl import __version__
from cyberdrop_dl.data_structures.supported_domains import SUPPORTED_FORUMS, SUPPORTED_WEBSITES
from cyberdrop_dl.scraper.filters import cache_filter_fn
from cyberdrop_dl.utils import yaml

if TYPE_CHECKING:
    from pathlib import Path

_cache: dict[str, Any] = {}
_cache_file: Path
_request_cache: SQLiteBackend = None  # type: ignore
DEFAULT_CONFIG_KEY = "default_config"


def startup(cache_file: Path) -> None:
    """Ensures that the cache file exists."""
    global _cache_file
    _cache_file = cache_file
    if not _cache_file.is_file():
        save(DEFAULT_CONFIG_KEY, "Default")

    load()


def load() -> None:
    """Loads the cache file into memory."""
    global _cache
    _cache = yaml.load(_cache_file)


def load_request_cache(
    cache_db: Path, file_host_cache_expire_after: timedelta, forum_cache_expire_after: timedelta
) -> None:
    global _request_cache
    urls_expire_after = {"*.simpcity.su": file_host_cache_expire_after}
    for host in SUPPORTED_WEBSITES.values():
        match_host = f"*.{host}" if "." in host else f"*.{host}.*"
        urls_expire_after[match_host] = file_host_cache_expire_after

    for forum in SUPPORTED_FORUMS.values():
        urls_expire_after[forum] = forum_cache_expire_after

    _request_cache = SQLiteBackend(
        cache_name=cache_db,  # type: ignore
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


def get(key: str) -> Any:
    """Returns the value of a key in the cache."""
    return _cache.get(key, None)


def save(key: str, value: Any) -> None:
    """Saves a key and value to the cache."""
    _cache[key] = value
    yaml.save(_cache_file, _cache)


def dump(data: dict[str, Any]) -> None:
    """dumps the dictionary into the cache"""
    _cache = data
    yaml.save(_cache_file, _cache)


def remove(key: str) -> None:
    """Removes a key from the cache."""
    if key in _cache:
        del _cache[key]
        yaml.save(_cache_file, _cache)


async def close() -> None:
    if _request_cache:
        await _request_cache.close()
    save("version", __version__)
