from __future__ import annotations

from aiolimiter import AsyncLimiter

from cyberdrop_dl import config


class DownloadSpeedLimiter(AsyncLimiter):
    def __init__(self, _=None) -> None:
        self.download_speed_limit = config.global_settings.rate_limiting_options.download_speed_limit
        self.chunk_size = 1024 * 1024 * 10  # 10MB
        if self.download_speed_limit:
            self.chunk_size = min(self.chunk_size, self.download_speed_limit)
        super().__init__(self.download_speed_limit, 1)

    async def acquire(self, amount: float | None = None) -> None:
        if self.download_speed_limit <= 0:
            return
        if not amount:
            amount = self.chunk_size
        await super().acquire(amount)
