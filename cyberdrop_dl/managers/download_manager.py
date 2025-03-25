from __future__ import annotations

import asyncio
from base64 import b64encode
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from cyberdrop_dl.clients.download_client import check_file_duration
from cyberdrop_dl.clients.errors import InsufficientFreeSpaceError
from cyberdrop_dl.utils.constants import FILE_FORMATS
from cyberdrop_dl.utils.logger import log_debug

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


class FileLocksVault:
    """Is this necessary? No. But I want it."""

    def __init__(self) -> None:
        self._locked_files: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def get_lock(self, filename: str) -> AsyncGenerator:
        """Get filelock for the provided filename. Creates one if none exists"""
        log_debug(f"Checking lock for {filename}", 20)
        if filename not in self._locked_files:
            log_debug(f"Lock for {filename} does not exists", 20)

        self._locked_files[filename] = self._locked_files.get(filename, asyncio.Lock())
        async with self._locked_files[filename]:
            log_debug(f"Lock for {filename} acquired", 20)
            yield
            log_debug(f"Lock for {filename} released", 20)


class StorageManager:
    """Runs an infinite loop to keep an updated value of the available space on all storage devices."""

    def __init__(self, manager: Manager):
        self.manager = manager
        # all=True is required to make sure it works on most platforms. See: https://github.com/giampaolo/psutil/issues/2191
        # We query all of them initially but we only check on a loop the ones that we need (self.used_mounts)
        self.partitions = psutil.disk_partitions(all=True)
        self.mounts = [Path(p.mountpoint) for p in self.partitions]
        self.used_mounts: set[Path] = set()
        self.mounts_free_space: dict[Path, int] = {}
        self.total_data_written: int = 0
        self._mount_addition_locks: dict[Path, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._period = 2  # seconds
        self._checking_loop = asyncio.create_task(self.free_space_check_loop())
        self._required_free_space = manager.config_manager.global_settings_data.general.required_free_space

    def get_mount_point(self, folder: Path) -> Path | None:
        possible_mountpoints = [mount for mount in self.mounts if mount in folder.parents or mount == folder]
        if not possible_mountpoints:
            return  # Path does not exists, ex: disconnected USB drive

        return max(possible_mountpoints, key=lambda path: len(path.parts))

    async def has_free_space(self, folder: Path | None = None) -> bool:
        """Checks if there is enough free space on the drive to continue operating."""
        if not folder:
            folder = self.manager.path_manager.download_folder

        mount = self.get_mount_point(folder)
        if not mount:
            return False

        async with self._mount_addition_locks[mount]:
            if not self.mounts_free_space.get(mount):
                # Manually query this mount now. Next time it will be part of the loop
                result = await asyncio.to_thread(psutil.disk_usage, str(mount))
                self.mounts_free_space[mount] = result.free
                self.used_mounts.add(mount)

        return self.mounts_free_space[mount] > self._required_free_space

    async def free_space_check_loop(self) -> None:
        """Queries free space of all used mounts and updates internal dict"""

        last_check = -1
        await self.manager.states.RUNNING.wait()
        while True:
            # We could also update the values every 512MB of data written (MIN_REQUIRED_FREE_SPACE)
            # if self.data_writen // MIN_REQUIRED_FREE_SPACE <= last_check:
            #    continue
            # But every second is more accurate
            last_check += 1
            used_mounts = sorted(self.used_mounts)
            tasks = [asyncio.to_thread(psutil.disk_usage, str(mount)) for mount in used_mounts]
            results = await asyncio.gather(*tasks)
            for mount, result in zip(used_mounts, results, strict=True):
                self.mounts_free_space[mount] = result.free

            await asyncio.sleep(self._period)

    async def close(self) -> None:
        self._checking_loop.cancel()
        try:
            await self._checking_loop
        except asyncio.CancelledError:
            pass


class DownloadManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self._download_instances: dict = {}
        self.storage_manager = StorageManager(manager)
        self.file_locks = FileLocksVault()

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

    async def check_free_space(self, media_item: MediaItem) -> None:
        """Checks if there is enough free space on the drive to continue operating."""
        if not await self.storage_manager.has_free_space(media_item.download_folder):
            raise InsufficientFreeSpaceError(origin=media_item)

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
