from aiolimiter import AsyncLimiter

class LeakyBucket( AsyncLimiter):
    def __init__(self,manager):
        self.download_speed_limit = manager.config_manager.global_settings_data['Rate_Limiting_Options']['download_speed_limit']
        self.max_amount=1024*1024*10
        super().__init__(self.download_speed_limit*1024,1)
    async def acquire(self, amount: float = 1):
        if self.download_speed_limit<=0:
            return
        if not isinstance(amount, int):
            amount=len(amount)
        await super().acquire(amount)
    def has_capacity(self, amount: float = 1) -> bool:
        """Check if there is enough capacity remaining in the limiter

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
        #allows for one packet to be received until bucket empties
        if self._level>self.max_rate:
            return False
        return self._level + amount <= self.max_amount
