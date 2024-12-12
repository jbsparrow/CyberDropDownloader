from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class DownloadSpeedLimiter(AsyncLimiter):
    def __init__(self, manager: Manager) -> None:
        self.download_speed_limit = (
            manager.config_manager.global_settings_data.rate_limiting_options.download_speed_limit
        )
        super().__init__(self.download_speed_limit, 1)

    async def acquire(self, amount: float = 1) -> None:
        if self.download_speed_limit <= 0:
            return
        await super().acquire(amount)
