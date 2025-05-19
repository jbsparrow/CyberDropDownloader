from __future__ import annotations

import asyncio
from base64 import b64encode
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from cyberdrop_dl.clients.download_client import check_file_duration
from cyberdrop_dl.constants import FILE_FORMATS
from cyberdrop_dl.utils.logger import log_debug

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager


class FileLocksVault:
    """Is this necessary? No. But I want it."""

    def __init__(self) -> None:
        self._locked_files: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def get_lock(self, filename: str) -> AsyncGenerator:
        """Get filelock for the provided filename. Creates one if none exists"""
        log_debug(f"Checking lock for '{filename}'", 20)
        if filename not in self._locked_files:
            log_debug(f"Lock for '{filename}' does not exists", 20)

        self._locked_files[filename] = self._locked_files.get(filename, asyncio.Lock())
        async with self._locked_files[filename]:
            log_debug(f"Lock for '{filename}' acquired", 20)
            yield
            log_debug(f"Lock for '{filename}' released", 20)


class DownloadManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self._download_instances: dict = {}
        self.file_locks = FileLocksVault()

        self.download_limits = {
            "bunkr": 1,
            "bunkrr": 1,
            "cyberdrop": 1,
            "cyberfile": 1,
            "noodlemagazine": 2,
            "4chan": 1,
            "pixeldrain": 2,
            "xxxbunker": 2,
        }

    def get_download_limit(self, key: str) -> int:
        """Returns the download limit for a domain."""
        rate_limiting_options = self.manager.config_manager.global_settings_data.rate_limiting_options
        instances = self.download_limits.get(key, rate_limiting_options.max_simultaneous_downloads_per_domain)

        return min(
            instances,
            rate_limiting_options.max_simultaneous_downloads_per_domain,
        )

    @staticmethod
    def basic_auth(username: str, password: str) -> str:
        """Returns a basic auth token."""
        token = b64encode(f"{username}:{password}".encode()).decode("ascii")
        return f"Basic {token}"

    def check_allowed_filetype(self, media_item: MediaItem) -> bool:
        """Checks if the file type is allowed to download."""
        ignore_options = self.manager.config_manager.settings_data.ignore_options
        valid_extensions = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"] | FILE_FORMATS["Audio"]
        if media_item.ext.lower() in FILE_FORMATS["Images"] and ignore_options.exclude_images:
            return False
        if media_item.ext.lower() in FILE_FORMATS["Videos"] and ignore_options.exclude_videos:
            return False
        if media_item.ext.lower() in FILE_FORMATS["Audio"] and ignore_options.exclude_audio:
            return False
        return not (ignore_options.exclude_other and media_item.ext.lower() not in valid_extensions)

    def pre_check_duration(self, media_item: MediaItem) -> bool:
        """Checks if the download is above the maximum runtime."""
        if not media_item.duration:
            return True

        return check_file_duration(media_item, self.manager)
