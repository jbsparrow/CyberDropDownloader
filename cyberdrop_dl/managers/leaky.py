from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from aiolimiter.compat import wait_for

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class LeakyBucket(AsyncLimiter):
    def __init__(self, manager: Manager) -> None:
        self.download_speed_limit = (
            manager.config_manager.global_settings_data.rate_limiting_options.download_speed_limit
        )

        self.max_amount = 1024 * 1024 * 10
        super().__init__(self.download_speed_limit, 1)

    async def acquire(self, amount: float = 1) -> None:
        if self.download_speed_limit <= 0:
            return
        if not isinstance(amount, int):
            amount = len(amount)
        loop = asyncio.get_running_loop()
        task = asyncio.current_task(loop)
        assert task is not None
        while not self.has_capacity(amount):
            # wait for the next drip to have left the bucket
            # add a future to the _waiters map to be notified
            # 'early' if capacity has come up
            fut = loop.create_future()
            self._waiters[task] = fut
            with contextlib.suppress(TimeoutError):
                await wait_for(asyncio.shield(fut), 1 / self._rate_per_sec * amount, loop=loop)
            fut.cancel()
        self._waiters.pop(task, None)
        self._level += amount

    def has_capacity(self, amount: float = 1) -> bool:
        """Check if there is enough capacity remaining in the limiter.

        :param amount: How much capacity you need to be available.

        """
        self._leak()
        requested = self._level + amount
        # if there are tasks waiting for capacity, signal to the first
        # there there may be some now (they won't wake up until this task
        # yields with an await)
        if requested < self.max_rate:
            for fut in self._waiters.values():
                if not fut.done():
                    fut.set_result(True)
                    break
        # allows for one packet to be received until bucket empties
        if self._level > self.max_rate:
            return False
        return self._level + amount <= self.max_amount
