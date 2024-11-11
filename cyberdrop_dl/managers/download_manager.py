from __future__ import annotations

import asyncio
import contextlib
from base64 import b64encode
from shutil import disk_usage
from typing import TYPE_CHECKING

from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.logger import log_debug

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem


class FileLock:
    """Is this necessary? No. But I want it."""

    def __init__(self) -> None:
        self._locked_files = {}

    async def check_lock(self, filename: str) -> None:
        """Checks if the file is locked."""
        try:
            log_debug(f"Checking lock for {filename}", 40)
            await self._locked_files[filename].acquire()
            log_debug(f"Lock for {filename} acquired", 40)
        except KeyError:
            log_debug(f"Lock for {filename} does not exist", 40)
            self._locked_files[filename] = asyncio.Lock()
            await self._locked_files[filename].acquire()
            log_debug(f"Lock for {filename} acquired", 40)

    async def release_lock(self, filename: str) -> None:
        """Releases the file lock."""
        with contextlib.suppress(KeyError, RuntimeError):
            log_debug(f"Releasing lock for {filename}", 40)
            self._locked_files[filename].release()
            log_debug(f"Lock for {filename} released", 40)


class DownloadManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self._download_instances: dict = {}

        self.file_lock = FileLock()

        self.download_limits = {
            "bunkr": 1,
            "bunkrr": 1,
            "cyberdrop": 1,
            "cyberfile": 1,
            "pixeldrain": 2,
            "xxxbunker": 2,
        }

    def get_download_limit(self, key: str) -> int:
        """Returns the download limit for a domain."""
        if key in self.download_limits:
            instances = self.download_limits[key]
        else:
            instances = self.manager.config_manager.global_settings_data["Rate_Limiting_Options"][
                "max_simultaneous_downloads_per_domain"
            ]

        return min(
            instances,
            self.manager.config_manager.global_settings_data["Rate_Limiting_Options"][
                "max_simultaneous_downloads_per_domain"
            ],
        )

    @staticmethod
    def basic_auth(username: str, password: str) -> str:
        """Returns a basic auth token."""
        token = b64encode(f"{username}:{password}".encode()).decode("ascii")
        return f"Basic {token}"

    def check_free_space(self, folder: Path | None = None) -> bool:
        """Checks if there is enough free space on the drive to continue operating."""
        if not folder:
            folder = self.manager.path_manager.download_dir

        folder = folder.resolve()
        while not folder.is_dir() and folder.parents:
            folder = folder.parent

        # check if we reached an anchor (root) that does not exists, ex: disconnected USB drive
        if not folder.is_dir():
            return False
        free_space = disk_usage(folder).free
        free_space_gb = free_space / 1024**3
        return free_space_gb >= self.manager.config_manager.global_settings_data["General"]["required_free_space"]

    def check_allowed_filetype(self, media_item: MediaItem) -> bool:
        """Checks if the file type is allowed to download."""
        ignore_options = self.manager.config_manager.settings_data["Ignore_Options"]
        valid_extensions = FILE_FORMATS["Images"] | FILE_FORMATS["Videos"] | FILE_FORMATS["Audio"]
        if media_item.ext in FILE_FORMATS["Images"] and ignore_options["exclude_images"]:
            return False
        if media_item.ext in FILE_FORMATS["Videos"] and ignore_options["exclude_videos"]:
            return False
        if media_item.ext in FILE_FORMATS["Audio"] and ignore_options["exclude_audio"]:
            return False
        return not (
            self.manager.config_manager.settings_data["Ignore_Options"]["exclude_other"]
            and media_item.ext not in valid_extensions
        )
