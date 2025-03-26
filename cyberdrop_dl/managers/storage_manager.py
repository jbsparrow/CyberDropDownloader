from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from cyberdrop_dl.clients.errors import InsufficientFreeSpaceError
from cyberdrop_dl.utils.logger import log_debug

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


class StorageManager:
    """Runs an infinite loop to keep an updated value of the available space on all storage devices."""

    def __init__(self, manager: Manager):
        self.manager = manager
        # all=True is required to make sure it works on most platforms. See: https://github.com/giampaolo/psutil/issues/2191
        # We query all of them initially but we only check on a loop the ones that we need (self.used_mounts)
        self.partitions = psutil.disk_partitions(all=True)
        self.partitions_map = {Path(p.mountpoint): p for p in self.partitions}
        self.mounts = sorted(self.partitions_map.keys())
        self.used_mounts: set[Path] = set()
        self.mounts_free_space: dict[Path, int] = {}
        self.total_data_written: int = 0
        self.pause_if_no_free_space = True
        self._mount_addition_locks: dict[Path, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._period: int = 2  # seconds
        self._log_period: int = 10  # loops, AKA log every 20 (2x10) seconds,
        self._loop = asyncio.create_task(self.free_space_check_loop())
        self._updated = asyncio.Event()

    def get_mount_point(self, folder: Path) -> Path | None:
        possible_mountpoints = [mount for mount in self.mounts if mount in folder.parents or mount == folder]
        if not possible_mountpoints:
            return  # Path does not exists, ex: disconnected USB drive

        return max(possible_mountpoints, key=lambda path: len(path.parts))

    def get_used_mounts_stats(self) -> dict:
        data = {}
        for mount in self.used_mounts:
            data[mount] = self.partitions_map[mount]._asdict()
            data[mount]["free_space"] = self.mounts_free_space[mount]
        return data

    async def has_sufficient_space(self, media_item: MediaItem) -> bool:
        """Checks if there is enough free space to download this item"""

        if isinstance(media_item.mount_point, Path):
            mount = media_item.mount_point
        else:
            mount = self.get_mount_point(media_item.download_folder)
            if mount:
                media_item.mount_point = mount
            else:
                return False

        return await self.has_sufficient_space_mount(mount)

    async def has_sufficient_space_mount(self, mount: Path) -> bool:
        """Checks if there is enough free space in this mount point"""

        assert mount in self.mounts
        async with self._mount_addition_locks[mount]:
            if not self.mounts_free_space.get(mount):
                # Manually query this mount now. Next time it will be part of the loop
                result = await asyncio.to_thread(psutil.disk_usage, str(mount))
                self.mounts_free_space[mount] = result.free
                self.used_mounts.add(mount)

        return (
            self.mounts_free_space[mount] > self.manager.config_manager.global_settings_data.general.required_free_space
        )

    async def check_free_space(self, media_item: MediaItem, no_pause: bool = False) -> None:
        """Checks if there is enough free space on the drive to continue operating."""

        if not await self.has_sufficient_space(media_item):
            if self.pause_if_no_free_space and not no_pause:
                self.manager.states.RUNNING.clear()
                await self.manager.states.RUNNING.wait()
                return await self.check_free_space(media_item, no_pause=True)
            raise InsufficientFreeSpaceError(origin=media_item)

    async def free_space_check_loop(self) -> None:
        """Queries free space of all used mounts and updates internal dict"""

        last_check = -1
        while True:
            # We could also update the values every 512MB of data written (MIN_REQUIRED_FREE_SPACE)
            # if self.data_writen // MIN_REQUIRED_FREE_SPACE <= last_check:
            #    continue
            # But every second is more accurate
            await self.manager.states.RUNNING.wait()
            self._updated.clear()
            last_check += 1
            if self.used_mounts:
                used_mounts = sorted(self.used_mounts)
                tasks = [asyncio.to_thread(psutil.disk_usage, str(mount)) for mount in used_mounts]
                results = await asyncio.gather(*tasks)
                for mount, result in zip(used_mounts, results, strict=True):
                    self.mounts_free_space[mount] = result.free
                if last_check % self._log_period == 0:
                    log_debug({"Storage status": self.get_used_mounts_stats()})
            self._updated.set()
            await asyncio.sleep(self._period)

    async def reset(self):
        await self._updated.wait()  # Make sure a query is not running right now
        self.total_data_written = 0
        self.used_mounts = set()
        self.mounts_free_space = {}

    async def close(self) -> None:
        await self.reset()
        self._loop.cancel()
        try:
            await self._loop
        except asyncio.CancelledError:
            pass
